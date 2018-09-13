from __future__ import absolute_import
from __future__ import print_function
from __future__ import unicode_literals

import json
from datetime import datetime

from django.core.management import BaseCommand

from corehq.apps.app_manager.dbaccessors import get_app
from corehq.apps.users.models import WebUser


class Command(BaseCommand):

    def add_arguments(self, parser):
        parser.add_argument(
            'domain_app_id_pairs',
            help='A JSON list where each element has the format [<domain>, <app_id>]',
            type=json.loads,
        )
        parser.add_argument('username')

    def handle(self, domain_app_id_pairs, username, **options):
        user_id = WebUser.get_by_username(username).get_id
        comment = 'Generated via command line for build performance benchmarking.'
        for (domain, app_id) in domain_app_id_pairs:
            print("%s: %s" % (domain, app_id))
            with Timer():
                app = get_app(domain, app_id)
                errors = app.validate_app()
                assert not errors, errors
                copy = app.make_build(
                    comment=comment,
                    user_id=user_id,
                    previous_version=app.get_latest_app(released_only=False),
                )
                copy.save(increment_version=False)
            copy.delete()


class Timer(object):

    def __enter__(self):
        self.start = datetime.utcnow()

    def __exit__(self, exc_type, exc_value, traceback):
        print(datetime.utcnow() - self.start)