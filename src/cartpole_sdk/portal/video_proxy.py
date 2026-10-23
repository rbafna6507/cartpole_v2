"""Fixed-origin, read-only video relay; no browser-supplied URLs or credentials."""
import http.client
import time
from urllib.parse import urlsplit
from cartpole_sdk.sensing.stream import _DeadlineSocket, StreamDeadline

VIDEO_SECONDS=60


def relay_video(handler):
    origin=handler.server.camera_url
    if origin is None:
        handler._respond(503,{'error':'camera not configured'});return
    if not handler.server.video_slots.acquire(blocking=False):
        handler._respond(429,{'error':'camera viewer limit reached'});return
    connection=None;response=None;started=False
    deadline=time.monotonic()+VIDEO_SECONDS
    try:
        parts=urlsplit(origin)
        factory=http.client.HTTPSConnection if parts.scheme=='https' else http.client.HTTPConnection
        connection=factory(parts.hostname,parts.port,timeout=min(3,VIDEO_SECONDS))
        connection.response_class=lambda sock,*args,**kwargs: http.client.HTTPResponse(
            _DeadlineSocket(sock,deadline=deadline,timeout_s=3,clock=time.monotonic),*args,**kwargs)
        # Fixed endpoint only. No redirects, cookies, or portal bearer forwarded.
        connection.request('GET','/video.h264',headers={'Accept':'application/octet-stream'})
        response=connection.getresponse()
        if response.status!=200 or response.getheader('Content-Type','').split(';')[0]!='application/octet-stream':
            handler._respond(502,{'error':'camera video unavailable'});return
        handler.send_response(200)
        handler.send_header('Content-Type','application/octet-stream')
        handler.send_header('Cache-Control','no-store')
        handler.send_header('X-Content-Type-Options','nosniff')
        handler.send_header('X-Accel-Buffering','no')
        handler.send_header('Connection','close')
        handler.end_headers();started=True
        handler.connection.settimeout(3)
        remaining_bytes=64*1024*1024
        while time.monotonic()<deadline and remaining_bytes>0:
            data=response.read1(min(65536,remaining_bytes))
            if not data:break
            handler.wfile.write(data);remaining_bytes-=len(data)
    except (OSError,http.client.HTTPException,StreamDeadline):
        if not started:handler._respond(502,{'error':'camera video unavailable'})
    finally:
        handler.close_connection=True
        if response is not None:response.close()
        if connection is not None:connection.close()
        handler.server.video_slots.release()
