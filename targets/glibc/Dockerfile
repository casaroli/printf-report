FROM debian:trixie
RUN apt-get update && apt-get install -y --no-install-recommends gcc libc6-dev locales && \
    sed -i -e 's/# en_US.UTF-8/en_US.UTF-8/' -e 's/# de_DE.UTF-8/de_DE.UTF-8/' /etc/locale.gen && locale-gen && \
    rm -rf /var/lib/apt/lists/*
