from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'^ws/rescue/(?P<sos_id>[^/]+)/$', consumers.RescueTrackingConsumer.as_asgi()),
]
