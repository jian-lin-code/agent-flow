# deploy/docker/postgres/Dockerfile
FROM pgvector/pgvector:pg16

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc make wget ca-certificates postgresql-server-dev-16 bzip2 \
 && rm -rf /var/lib/apt/lists/*

RUN wget -q http://www.xunsearch.com/scws/down/scws-1.2.3.tar.bz2 \
 && tar xjf scws-1.2.3.tar.bz2 \
 && cd scws-1.2.3 && ./configure && make install \
 && cd .. && rm -rf scws-1.2.3*

# 这里加了 ghproxy 加速，服务器上秒下
RUN wget -q https://ghproxy.net/https://github.com/amutu/zhparser/archive/refs/heads/master.tar.gz -O zh.tar.gz \
 && tar xzf zh.tar.gz \
 && cd zhparser-master && make && make install \
 && cd .. && rm -rf zh.tar.gz zhparser-master