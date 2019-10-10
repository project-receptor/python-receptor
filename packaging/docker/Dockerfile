FROM centos:8

ADD https://github.com/krallin/tini/releases/download/v0.18.0/tini /bin/tini
ADD packaging/docker/entrypoint.sh /bin/entrypoint
ADD packaging/docker/receptor.conf /tmp/receptor.conf
RUN yum install -y python36 python3-dateutil
ADD dist/receptor-0.1.0-py2.py3-none-any.whl /tmp/receptor-0.1.0-py2.py3-none-any.whl
RUN pip3 install /tmp/receptor-0.1.0-py2.py3-none-any.whl
RUN mkdir -p /receptor && \
    chmod +x /bin/tini /bin/entrypoint && \
    rm -rf /var/cache/yum
VOLUME /receptor
ENV LANG=en_US.UTF-8
ENV LANGUAGE=en_US:en
ENV LC_ALL=en_US.UTF-8
ENV HOME=/receptor
EXPOSE 8888/tcp
WORKDIR /receptor
ENTRYPOINT ["entrypoint"]
CMD ["receptor", "-c", "/receptor/receptor.conf", "node"]
