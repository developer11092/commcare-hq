import hashlib
from abc import abstractmethod, ABCMeta
from datetime import datetime

import six
from couchdbkit import ResourceNotFound

from corehq.util.couch_helpers import PaginateViewLogHandler, paginate_view

DOC_PROCESSOR_ITERATION_KEY_PREFIX = "-doc-processor"


class ResumableDocsByTypeIterator(object):
    """Perform one-time resumable iteration over documents by type

    Iteration can be efficiently stopped and resumed. The iteration may
    omit documents that are added after the iteration begins or resumes
    and may include deleted documents.

    :param db: Couchdb database.
    :param doc_types: A list of doc type names to iterate on.
    :param iteration_key: A unique key identifying the iteration. This
    key will be used in combination with `doc_types` to maintain state
    about an iteration that is in progress. The state will be maintained
    indefinitely unless it is removed with `discard_state()`.
    :param chunk_size: Number of documents to yield before updating the
    iteration checkpoint. In the worst case about this many documents
    that were previously yielded may be yielded again if the iteration
    is stopped and later resumed.
    """

    def __init__(self, db, doc_types, iteration_key, chunk_size=100):
        if isinstance(doc_types, str):
            raise TypeError("expected list of strings, got %r" % (doc_types,))
        self.db = db
        self.original_doc_types = doc_types = sorted(doc_types)
        self.iteration_key = iteration_key
        self.chunk_size = chunk_size
        iteration_name = "{}/{}".format(iteration_key, " ".join(doc_types))
        self.iteration_id = hashlib.sha1(iteration_name).hexdigest()
        try:
            self.state = db.get(self.iteration_id)
        except ResourceNotFound:
            # new iteration
            self.state = {
                "_id": self.iteration_id,
                "doc_type": "ResumableDocsByTypeIteratorState",
                "retry": {},

                # for humans
                "name": iteration_name,
                "timestamp": datetime.utcnow().isoformat()
            }
            args = {}
        else:
            # resume iteration
            args = self.state.get("offset", {}).copy()
            if args:
                assert args.get("startkey"), args
                doc_type = args["startkey"][0]
                # skip doc types before offset
                doc_types = doc_types[doc_types.index(doc_type):]
            else:
                # non-retry phase of iteration is complete
                doc_types = []
        args.update(
            view_name='all_docs/by_doc_type',
            chunk_size=chunk_size,
            log_handler=ResumableDocsByTypeLogHandler(self),
            include_docs=True,
            reduce=False,
        )
        self.view_args = args
        self.doc_types = doc_types

    def __iter__(self):
        args = self.view_args
        for doc_type in self.doc_types:
            if args.get("startkey", [None])[0] != doc_type:
                args.pop("startkey_docid", None)
                args["startkey"] = [doc_type]
            args["endkey"] = [doc_type, {}]
            for result in paginate_view(self.db, **args):
                yield result['doc']

        retried = {}
        while self.state["retry"] != retried:
            for doc_id, retries in list(self.state["retry"].iteritems()):
                if retries == retried.get(doc_id):
                    continue  # skip already retried (successfully)
                retried[doc_id] = retries
                try:
                    yield self.db.get(doc_id)
                except ResourceNotFound:
                    pass

        # save iteration state without offset to signal completion
        self.state.pop("offset", None)
        self.state["retry"] = {}
        self._save_state()

    def retry(self, doc, max_retry=3):
        """Add document to be yielded at end of iteration

        Iteration order of retry documents is undefined. All retry
        documents will be yielded after the initial non-retry phase of
        iteration has completed, and every retry document will be
        yielded each time the iterator is stopped and resumed during the
        retry phase. This method is relatively inefficient because it
        forces the iteration state to be saved to couch. If you find
        yourself calling this for many documents during the iteration
        you may want to consider a different retry strategy.

        :param doc: The doc dict to retry. It will be re-fetched from
        the database before being yielded from the iteration.
        :param max_retry: Maximum number of times a given document may
        be retried.
        :raises: `TooManyRetries` if this method has been called too
        many times with a given document.
        """
        doc_id = doc["_id"]
        retries = self.state["retry"].get(doc_id, 0) + 1
        if retries > max_retry:
            raise TooManyRetries(doc_id)
        self.state["retry"][doc_id] = retries
        self._save_state()

    @property
    def progress_info(self):
        """Extra progress information

        This property can be used to store and retrieve extra progress
        information associated with the iteration. The information is
        persisted with the iteration state in couch.
        """
        return self.state.get("progress_info")

    @progress_info.setter
    def progress_info(self, info):
        self.state["progress_info"] = info
        self._save_state()

    def _save_state(self):
        self.state["timestamp"] = datetime.utcnow().isoformat()
        self.db.save_doc(self.state)

    def discard_state(self):
        try:
            self.db.delete_doc(self.iteration_id)
        except ResourceNotFound:
            pass
        self.__init__(
            self.db,
            self.original_doc_types,
            self.iteration_key,
            self.chunk_size,
        )


class ResumableDocsByTypeLogHandler(PaginateViewLogHandler):

    def __init__(self, iterator):
        self.iterator = iterator

    def view_starting(self, db, view_name, kwargs, total_emitted):
        offset = {k: v for k, v in kwargs.items() if k.startswith("startkey")}
        self.iterator.state["offset"] = offset
        self.iterator._save_state()


class TooManyRetries(Exception):
    pass


DOCS_SKIPPED_WARNING = """
        WARNING {} documents were not processed due to concurrent modification
        during migration. Run the migration again until you do not see this
        message.
        """


class BaseDocProcessor(six.with_metaclass(ABCMeta)):

    def __init__(self, slug):
        self.slug = slug

    def __enter__(self):
        pass

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    @abstractmethod
    def process_doc(self, doc, couchdb):
        """Migrate a single document

        :param doc: The document dict to be migrated.
        :param couchdb: Couchdb database in which to save migrated doc.
        :returns: True if doc was migrated else False. If this returns False
        the document migration will be retried later.
        """
        raise NotImplementedError

    def processing_complete(self, skipped):
        pass

    def filter(self, doc):
        """
        :param doc: the document to filter
        :return: True if this doc should be migrated
        """
        return True


class CouchDocumentProcessor(object):
    """Process Couch Docs

    :param slug: process name.
    :param doc_type_map: Dict of `doc_type_name: model_class` pairs.
    :param doc_processor: A `BaseDocProcessor` object used to
    process documents.
    :param reset: Reset existing processor state (if any), causing all
    documents to be reconsidered for processing, if this is true.
    :param max_retry: Number of times to retry processing a document
    before giving up.
    :param chunk_size: Maximum number of records to read from couch at
    one time. It may be necessary to use a smaller chunk size if the
    records being processed are very large and the default chunk size of
    100 would exceed available memory.
    """
    def __init__(self, doc_type_map, doc_processor, reset=False, max_retry=2, chunk_size=100):
        self.doc_type_map = doc_type_map
        self.doc_processor = doc_processor
        self.reset = reset
        self.max_retry = max_retry
        self.chunk_size = chunk_size

        self.couchdb = next(iter(doc_type_map.values())).get_db()
        assert all(m.get_db() is self.couchdb for m in doc_type_map.values()), \
            "documents must live in same couch db: %s" % repr(doc_type_map)

        iter_key = doc_processor.slug + DOC_PROCESSOR_ITERATION_KEY_PREFIX
        self.docs_by_type = ResumableDocsByTypeIterator(self.couchdb, doc_type_map, iter_key,
                                                   chunk_size=chunk_size)

    def has_started(self):
        return bool(self.docs_by_type.progress_info)

    def run(self):
        """
        :returns: A tuple `(<num processed>, <num skipped>)`
        """
        from corehq.dbaccessors.couchapps.all_docs import get_doc_count_by_type

        total = sum(get_doc_count_by_type(self.couchdb, doc_type)
                    for doc_type in self.doc_type_map)
        processed = 0
        skipped = 0
        visited = 0
        previously_visited = 0

        if self.reset:
            self.docs_by_type.discard_state()
        elif self.docs_by_type.progress_info:
            info = self.docs_by_type.progress_info
            old_total = info["total"]
            # Estimate already visited based on difference of old/new
            # totals. The theory is that new or deleted records will be
            # evenly distributed across the entire set.
            visited = int(round(float(total) / old_total * info["visited"]))
            previously_visited = visited
        print("Processing {} documents{}: {}...".format(
            total,
            " (~{} already processed)".format(visited) if visited else "",
            ", ".join(sorted(self.doc_type_map))
        ))

        with self.doc_processor:
            start = datetime.now()
            for doc in self.docs_by_type:
                visited += 1
                if visited % self.chunk_size == 0:
                    self.docs_by_type.progress_info = {"visited": visited, "total": total}
                if self.doc_processor.filter(doc):
                    ok = self.doc_processor.process_doc(doc, self.couchdb)
                    if ok:
                        processed += 1
                    else:
                        try:
                            self.docs_by_type.retry(doc, self.max_retry)
                        except TooManyRetries:
                            print("Skip: {doc_type} {_id}".format(**doc))
                            skipped += 1
                    if (processed + skipped) % self.chunk_size == 0:
                        elapsed = datetime.now() - start
                        session_visited = visited - previously_visited
                        session_total = total - previously_visited
                        if session_visited > session_total:
                            remaining = "?"
                        else:
                            session_remaining = session_total - session_visited
                            remaining = elapsed / session_visited * session_remaining
                        print("Processed {}/{} of {} documents in {} ({} remaining)"
                              .format(processed, visited, total, elapsed, remaining))

        self.doc_processor.processing_complete(skipped)

        print("Processed {}/{} of {} documents ({} previously processed, {} filtered out)."
            .format(
                processed,
                visited,
                total,
                total - visited,
                visited - (processed + skipped)
            ))
        if skipped:
            print(DOCS_SKIPPED_WARNING.format(skipped))
        return processed, skipped

