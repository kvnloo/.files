# Headless Blender 5.2.3 for Cycles GPU renders in the shared blender sandbox. Runs as uid 1000 (restricted PSS).
FROM ubuntu:24.04
ARG BL=blender-5.2.3-linux-x64
ARG MIRROR=https://mirrors.ocf.berkeley.edu/blender/release/Blender5.2
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl xz-utils \
      libxi6 libxxf86vm1 libxfixes3 libxrender1 libxkbcommon0 libsm6 libice6 libgl1 libegl1 libglu1-mesa \
      libx11-6 libxext6 libxcursor1 libxinerama1 libxrandr2 libwayland-client0 libdbus-1-3 ffmpeg python3-numpy \
 && curl -fsSL "$MIRROR/$BL.tar.xz" | tar -xJ -C /opt && ln -s /opt/$BL/blender /usr/local/bin/blender \
 && apt-get purge -y curl xz-utils && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*
ENV NVIDIA_DRIVER_CAPABILITIES=compute,utility,graphics HOME=/tmp
USER 1000:1000
WORKDIR /project
ENTRYPOINT ["blender", "-b", "--factory-startup"]
