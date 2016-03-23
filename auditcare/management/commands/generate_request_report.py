import csv
import re
from optparse import make_option

from django.contrib.auth.models import User
from django.core.management.base import LabelCommand

from corehq.apps.users.models import WebUser
from dimagi.utils.couch.database import iter_docs

from auditcare.models import NavigationEventAudit


def navigation_event_ids_by_user(user):
    database = NavigationEventAudit.get_db()

    return {row['id'] for row in database.view('auditcare/urlpath_by_user_date',
        startkey=[user ],
        endkey=[user, {}],
        reduce=False,
        include_docs=False,
    )}

def request_was_made_to_domain(domain, request_path):
    return request_path.startswith('/a/' + domain + '/')

def get_users(domain, no_superuser=False):
    users = [u.username for u in WebUser.by_domain(domain)]
    if not no_superuser:
        super_users = [u['username'] for u in User.objects.filter(is_superuser=True).values('username')]
    return set(users + super_users)

class Command(LabelCommand):
    args = 'domain filename'
    help = """Generate request report"""
    option_list = LabelCommand.option_list +\
                  (make_option('--no-superuser', action='store_true', dest='no_superuser', default=False,
                      help="Include superusers in report"),)

    def handle(self, *args, **options):
        domain, filename = args
        no_superuser = options["no_superuser"]

        users = get_users(domain, no_superuser)

        with open(filename, 'wb') as csvfile:
            writer = csv.writer(csvfile)
            for user in users:
                for event in iter_docs(NavigationEventAudit.get_db(), navigation_event_ids_by_user(user)):
                    doc = NavigationEventAudit.wrap(event)
                    if request_was_made_to_domain(domain, doc.request_path):
                        writer.writerow([doc.user, doc.event_date, doc.ip_address, doc.request_path])
