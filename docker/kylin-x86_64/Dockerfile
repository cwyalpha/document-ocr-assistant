FROM macrosan/kylin:v10-sp1

ARG PYTHON_VERSION=3.12.13
ARG PYTHON_SHA256=c08bc65a81971c1dd5783182826503369466c7e67374d1646519adf05207b684

RUN test "$(uname -m)" = "x86_64" \
    && dnf -y install \
      bash binutils bzip2 bzip2-devel cpio curl dbus-libs expat-devel file \
      findutils fontconfig freetype gcc gcc-c++ gdbm-devel gzip libatomic \
      libffi-devel libnsl2-devel libtirpc-devel libxkbcommon libxkbcommon-x11 \
      make mesa-libGL ncurses-devel openssl-devel readline-devel \
      rpm-build sqlite-devel tar tk-devel util-linux-devel which \
      xcb-util xcb-util-image xcb-util-keysyms xcb-util-renderutil xcb-util-wm \
      xz xz-devel zlib-devel \
    && dnf clean all \
    && rm -rf /var/cache/dnf

RUN curl -fsSLo /tmp/Python.tar.xz \
      "https://www.python.org/ftp/python/${PYTHON_VERSION}/Python-${PYTHON_VERSION}.tar.xz" \
    && echo "${PYTHON_SHA256}  /tmp/Python.tar.xz" | sha256sum -c - \
    && mkdir -p /tmp/python-source \
    && tar -xJf /tmp/Python.tar.xz -C /tmp/python-source --strip-components=1 \
    && cd /tmp/python-source \
    && ./configure \
      --prefix=/opt/python312 \
      --enable-shared \
      --with-ensurepip=install \
      --with-openssl=/usr \
    && make -j"$(getconf _NPROCESSORS_ONLN)" \
    && make altinstall \
    && rm -rf /tmp/python-source /tmp/Python.tar.xz

ENV PATH=/opt/python312/bin:${PATH}
ENV LD_LIBRARY_PATH=/opt/python312/lib
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
ENV PIP_NO_CACHE_DIR=1

COPY requirements-kylin.txt requirements-table.txt /tmp/document-ocr-requirements/
RUN python3.12 -m pip install --upgrade pip setuptools wheel \
    && python3.12 -m pip install \
      -r /tmp/document-ocr-requirements/requirements-kylin.txt \
      -r /tmp/document-ocr-requirements/requirements-table.txt \
      "pyinstaller==6.18.0" \
      "pyinstaller-hooks-contrib==2026.0" \
      "pytest>=7.4,<9"

WORKDIR /workspace
