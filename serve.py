# Static file server for the thread browser. Same as `python -m http.server` plus a proper
# content ETag: each file gets a hash of its bytes, and an `If-None-Match` that matches is
# answered with 304 (no body). So after a redeploy only files whose content actually changed
# re-transfer, and Cloudflare (set to respect origin headers) revalidates instead of serving
# a stale module -- which is what was pairing a fresh index.html with an old layout.js.
#
# Cache-Control: max-age=0, must-revalidate forces that revalidation on every request without
# disabling caching -- the 304 path still applies. (It's the no-cache behaviour without the
# no-cache token; change the one constant below if you want a real max-age later.)
import functools, hashlib, os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

CACHE_CONTROL = "max-age=0, must-revalidate"


class Handler(SimpleHTTPRequestHandler):
    _etags = {}   # path -> ((mtime_ns, size), etag); recomputed only when the file changes

    def _etag(self, path):
        if os.path.isdir(path):
            path = os.path.join(path, "index.html")   # a dir request ("/") is served as its index.html
        try:
            st = os.stat(path)
        except OSError:
            return None
        key = (st.st_mtime_ns, st.st_size)
        hit = self._etags.get(path)
        if hit and hit[0] == key:
            return hit[1]
        h = hashlib.blake2b(digest_size=16)
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 16), b""):
                h.update(chunk)
        tag = '"%s"' % h.hexdigest()
        self._etags[path] = (key, tag)
        return tag

    def send_head(self):
        self._tag = self._etag(self.translate_path(self.path))
        if self._tag and self.headers.get("If-None-Match") == self._tag:
            self.send_response(304)
            self.end_headers()   # adds ETag + Cache-Control below
            return None
        return super().send_head()

    def end_headers(self):
        if getattr(self, "_tag", None):
            self.send_header("ETag", self._tag)
        self.send_header("Cache-Control", CACHE_CONTROL)
        super().end_headers()


ThreadingHTTPServer(("", 8000), functools.partial(Handler, directory="/site")).serve_forever()
