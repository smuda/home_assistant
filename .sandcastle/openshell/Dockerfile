# Agent image for the OpenShell sandbox provider. Build it with:
#   docker build -t sandcastle-openshell:latest .sandcastle/openshell
#
# OpenShell's baseline policy grants read-only /usr, /lib, /etc and
# read-write /sandbox, /tmp, and runs processes as user "sandbox", so
# the user's home is /sandbox and everything the agent writes lives there.
FROM node:22-bookworm-slim@sha256:e9f565d32859f0cbfb52125eafe8be39390f24dac302dc3cdf566e8ba3ab21ee

# iproute2: OpenShell's supervisor sets up the sandbox network namespace.
# python3, python3-yaml, python3-jinja2: for the repo's unittest suites,
# installed from apt so nothing is fetched at run time.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      git ca-certificates bash iproute2 \
      python3 python3-yaml python3-jinja2 \
 && rm -rf /var/lib/apt/lists/*

RUN npm install -g @anthropic-ai/claude-code@2.1.328 \
 && npm cache clean --force

RUN groupadd --gid 1001 sandbox \
 && useradd --uid 1001 --gid sandbox --home-dir /sandbox --create-home \
      --shell /bin/bash sandbox

# No setuid/setgid binary to escalate through.
RUN find / -xdev -perm /6000 -type f -exec chmod a-s {} +

ENV HOME=/sandbox \
    CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1 \
    DISABLE_AUTOUPDATER=1

USER sandbox
WORKDIR /sandbox
