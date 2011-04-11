from django.conf.urls.defaults import *

urlpatterns = patterns('corehq.apps.cleanup.views',
    # stub urls
    #(r'', 'links'),
    (r'submissions.json', 'submissions_json'),
    (r'users.json', 'users_json'),
    (r'^submissions/', 'submissions'),
    (r'^relabel_submissions/', 'relabel_submissions'),
)