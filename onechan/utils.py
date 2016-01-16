import json
from django_redis import get_redis_connection
from django.conf import settings
from django.core.cache import cache
from datetime import datetime, timedelta
from .models import Smiley

def notify(msg):
    conn = get_redis_connection('default')
    conn.publish(settings.WS_REDIS_CHANNEL, json.dumps(msg))

def stats(request):
    conn = get_redis_connection('default')
    return {
        'stats_today_users': conn.scard('stats_today_users'),
        'stats_today_posts': conn.get('stats_today_posts'),
        'stats_speed': cache.get('stats_speed')
    }

def get_tomorrow(dt=None):
    if not dt:
        dt = datetime.now()
    td = timedelta(days=1, hours=-dt.hour, minutes=-dt.minute, seconds=-dt.second)
    return dt + td


def incr_today_posts():
    conn = get_redis_connection('default')
    conn.incr('stats_today_posts')
    conn.expireat('stats_today_posts', get_tomorrow())


class SmileyCacheMiddleware(object):

    def process_request(self, request):
        cache.set('smiley_list',
            { s.name: s.img.url for s in Smiley.objects.all() },
            timeout=None
        )

    def process_response(self, request, response):
        cache.delete('smiley_list')
        return response


class DailyUsersMiddleware(object):

    def process_request(self, request):
        host = request.META['REMOTE_ADDR']
        conn = get_redis_connection('default')
        conn.sadd('stats_today_users', host)
        conn.expireat('stats_today_users', get_tomorrow())
