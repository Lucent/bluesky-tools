# Two-stage build: the first stage parses the archive into index.json and assembles the
# static site; the runtime image carries only /site and python, and just serves it.
FROM python:3.12-slim AS build
ARG ARCHIVE_DID
WORKDIR /src
COPY thread_browser.py thread_graph.py browse.html flextree.js layout.js layout-lab.html ./
COPY ${ARCHIVE_DID}/ ./${ARCHIVE_DID}/
RUN mkdir /site && \
    SUFFIX="${ARCHIVE_DID#did:plc:}" && \
    python thread_browser.py ${ARCHIVE_DID} --out "/site/${SUFFIX}.json" && \
    sed "s|__ARCHIVE_FILE__|${SUFFIX}.json|" browse.html > /site/index.html && \
    cp flextree.js layout.js layout-lab.html /site/

FROM python:3.12-slim
COPY --from=build /site /site
WORKDIR /site
USER nobody
EXPOSE 8000
CMD ["python", "-m", "http.server", "8000"]
