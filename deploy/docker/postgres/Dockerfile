FROM pgvector/pgvector:pg16

# 换阿里云源，加速 apt-get
RUN sed -i 's|deb.debian.org|mirrors.aliyun.com|g' /etc/apt/sources.list \
 && sed -i 's|security.debian.org|mirrors.aliyun.com|g' /etc/apt/sources.list \
 && apt-get update && apt-get install -y --no-install-recommends \
    gcc make ca-certificates postgresql-server-dev-16 bzip2 \
 && rm -rf /var/lib/apt/lists/*

# 复制本地传上来的 SCWS 压缩包
COPY scws-1.2.3.tar.bz2 /tmp/
RUN cd /tmp && tar xjf scws-1.2.3.tar.bz2 \
 && cd scws-1.2.3 && ./configure && make install \
 && cd /tmp && rm -rf scws-1.2.3*

# 复制本地传上来的 zhparser 压缩包
COPY zhparser.tar.gz /tmp/
RUN cd /tmp && tar xzf zhparser.tar.gz \
 && cd zhparser-master && make && make install \
 && cd /tmp && rm -rf zhparser.tar.gz zhparser-master