# Fisherman and its Redmine plug-in. The model server is not part of this image: run llama-server
# natively (on a Mac, Docker cannot use the GPU) and point the configuration at it.

FROM python:3.14-slim@sha256:fbecd461fc72d21b2143c6eaba25143738079154a6d0ea3da3aec724f50eed4a AS build

WORKDIR /src
COPY pyproject.toml README.md LICENSE ./
COPY fisherman ./fisherman
COPY plugins/fisherman-redmine ./plugins/fisherman-redmine
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /wheels . ./plugins/fisherman-redmine

FROM python:3.14-slim@sha256:fbecd461fc72d21b2143c6eaba25143738079154a6d0ea3da3aec724f50eed4a

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY --from=build /wheels /tmp/wheels
RUN pip install --no-cache-dir --no-deps /tmp/wheels/*.whl \
    && rm -rf /tmp/wheels \
    && useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin fisherman \
    && mkdir -p /state \
    && chown 10001:10001 /state

# /config: the private configuration, prompts and keys (mount read-only)
# /state: the scanner's checkpoints (a named volume inherits this directory's owner)
VOLUME ["/state"]
USER 10001:10001

ENTRYPOINT ["fisherman"]
CMD ["run", "--config", "/config/config.json"]
