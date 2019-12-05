FROM python:3 AS builder
COPY receptor setup.* LICENSE.md README.md /receptor/
WORKDIR /receptor
RUN python setup.py bdist_wheel

FROM fedora:31

COPY --from=builder /receptor/dist/receptor-*.whl /tmp/
ADD https://github.com/krallin/tini/releases/latest/download/tini /bin/tini
ADD packaging/docker/entrypoint.sh /bin/entrypoint
ADD packaging/docker/receptor.conf /tmp/receptor.conf

RUN dnf update -y &&\
    dnf install -y python3 python3-pip &&\
    dnf clean all

RUN chmod +x /bin/tini /bin/entrypoint &&\
    rm -rf /var/cache/yum

RUN pip3 install --no-cache-dir python-dateutil &&\
    pip3 install --no-cache-dir /tmp/receptor-*.whl &&\
    rm /tmp/receptor-*.whl

RUN mkdir /var/lib/receptor
VOLUME /var/lib/receptor

ENV LANG=en_US.UTF-8
ENV LANGUAGE=en_US:en
ENV LC_ALL=en_US.UTF-8
ENV HOME=/var/lib/receptor
EXPOSE 8888/tcp
WORKDIR /var/lib/receptor
ENTRYPOINT ["entrypoint"]
CMD ["receptor", "-c", "/var/lib/receptor/receptor.conf", "node"]
