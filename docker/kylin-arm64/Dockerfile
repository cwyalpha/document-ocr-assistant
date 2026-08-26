FROM macrosan/kylin:v10-sp1

ARG PYTHON_VERSION=3.10.18
ARG PYTHON_SHA256=ae665bc678abd9ab6a6e1573d2481625a53719bc517e9a634ed2b9fefae3817f
ARG QT_VERSION=5.15.2
ARG QTBASE_SHA256=909fad2591ee367993a75d7e2ea50ad4db332f05e1c38dd7a5a274e156a4e0f8
ARG PYSIDE_VERSION=5.15.2.1
ARG PYSIDE_SHA256=91e78e4e3b31ebb0053c2e4f1029703e578615695450c0dd03072248d713b391

RUN test "$(uname -m)" = "aarch64" \
    && dnf -y install \
      bash binutils bzip2 bzip2-devel clang clang-devel cmake cpio curl \
      cups-devel dbus-devel dbus-libs expat-devel file findutils fontconfig \
      fontconfig-devel freetype freetype-devel gcc gcc-c++ gdbm-devel git \
      glib2-devel gzip libX11-devel libX11-xcb libXcursor-devel \
      libXext-devel libXfixes-devel libXi-devel libXrandr-devel libXrender-devel \
      libatomic libffi-devel libnsl2-devel libtirpc-devel libxkbcommon \
      libxkbcommon-devel libxkbcommon-x11 libxkbcommon-x11-devel libxcb-devel \
      libreoffice-core libreoffice-langpack-zh-Hans libreoffice-writer llvm \
      llvm-devel make mesa-libGL mesa-libGL-devel ncurses-devel ninja-build \
      openssl-devel readline-devel rpm-build sqlite-devel tar tk-devel \
      unrar util-linux-devel which xcb-util xcb-util-devel xcb-util-image \
      xcb-util-image-devel xcb-util-keysyms xcb-util-keysyms-devel \
      xcb-util-renderutil xcb-util-renderutil-devel xcb-util-wm xcb-util-wm-devel \
      xz xz-devel zlib-devel \
    && dnf clean all \
    && mkdir -p /usr/lib \
    && ln -s /usr/lib64/clang /usr/lib/clang \
    && rm -rf /var/cache/dnf

RUN curl -fsSLo /tmp/Python.tar.xz \
      "https://www.python.org/ftp/python/${PYTHON_VERSION}/Python-${PYTHON_VERSION}.tar.xz" \
    && echo "${PYTHON_SHA256}  /tmp/Python.tar.xz" | sha256sum -c - \
    && mkdir -p /tmp/python-source \
    && tar -xJf /tmp/Python.tar.xz -C /tmp/python-source --strip-components=1 \
    && cd /tmp/python-source \
    && ./configure \
      --prefix=/opt/python310 \
      --enable-shared \
      --with-ensurepip=install \
      --with-openssl=/usr \
    && make -j"$(getconf _NPROCESSORS_ONLN)" \
    && make altinstall \
    && ln -s /opt/python310/bin/python3.10 /opt/python310/bin/python3 \
    && rm -rf /tmp/python-source /tmp/Python.tar.xz

ENV PATH=/opt/python310/bin:/opt/qt515/bin:${PATH}
ENV LD_LIBRARY_PATH=/opt/python310/lib:/opt/qt515/lib
ENV PKG_CONFIG_PATH=/opt/qt515/lib/pkgconfig
ENV CMAKE_PREFIX_PATH=/opt/qt515
ENV QT_PLUGIN_PATH=/opt/qt515/plugins
ENV LLVM_INSTALL_DIR=/usr
ENV CLANG_INSTALL_DIR=/usr
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
ENV PIP_NO_CACHE_DIR=1

RUN curl -fsSLo /tmp/qtbase.tar.xz \
      "https://download.qt.io/archive/qt/5.15/${QT_VERSION}/submodules/qtbase-everywhere-src-${QT_VERSION}.tar.xz" \
    && echo "${QTBASE_SHA256}  /tmp/qtbase.tar.xz" | sha256sum -c - \
    && mkdir -p /tmp/qtbase-source /tmp/qtbase-build \
    && tar -xJf /tmp/qtbase.tar.xz -C /tmp/qtbase-source --strip-components=1 \
    && cd /tmp/qtbase-build \
    && /tmp/qtbase-source/configure \
      -prefix /opt/qt515 \
      -opensource -confirm-license -release -shared \
      -nomake examples -nomake tests \
      -xcb -fontconfig -system-freetype \
      -no-icu -no-gtk -no-feature-vulkan \
    && make -j"$(getconf _NPROCESSORS_ONLN)" \
    && make install \
    && rm -rf /tmp/qtbase-source /tmp/qtbase-build /tmp/qtbase.tar.xz

COPY packaging/pyside2-python310.patch /tmp/pyside2-python310.patch
RUN curl --retry 10 --retry-all-errors --retry-delay 2 -fsSLo /tmp/pyside.tar.gz \
      "https://download.qt.io/official_releases/QtForPython/pyside2/PySide2-${PYSIDE_VERSION}-src/pyside-setup-opensource-src-${PYSIDE_VERSION}.tar.gz" \
    && echo "${PYSIDE_SHA256}  /tmp/pyside.tar.gz" | sha256sum -c - \
    && mkdir -p /tmp/pyside-source \
    && tar -xJf /tmp/pyside.tar.gz -C /tmp/pyside-source --strip-components=1 \
    && patch -d /tmp/pyside-source -p1 < /tmp/pyside2-python310.patch \
    && cd /tmp/pyside-source \
    && python3.10 setup.py install \
      --qmake=/opt/qt515/bin/qmake \
      --parallel=4 \
      --module-subset=Core,Gui,Widgets \
    && python3.10 -c 'from PySide2 import QtCore, QtGui, QtWidgets; print(QtCore.qVersion())' \
    && rm -rf /tmp/pyside-source /tmp/pyside.tar.gz

COPY requirements-kylin-arm64.txt requirements-table.txt /tmp/document-ocr-requirements/
RUN python3.10 -m pip install \
      -r /tmp/document-ocr-requirements/requirements-kylin-arm64.txt \
      -r /tmp/document-ocr-requirements/requirements-table.txt \
      "pyinstaller==6.18.0" \
      "pyinstaller-hooks-contrib==2026.0" \
      "pytest>=7.4,<9"

WORKDIR /workspace
