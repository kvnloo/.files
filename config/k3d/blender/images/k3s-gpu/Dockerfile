# k3s node image with the NVIDIA container runtime (k3d GPU recipe, Ubuntu base so glibc tools work).
# k3s auto-detects /usr/bin/nvidia-container-runtime and registers RuntimeClass "nvidia".
ARG K3S_TAG=v1.35.5-k3s1
ARG CUDA_TAG=12.6.0-base-ubuntu24.04
FROM rancher/k3s:${K3S_TAG} AS k3s
FROM nvidia/cuda:${CUDA_TAG}
RUN apt-get update && apt-get install -y --no-install-recommends curl gnupg ca-certificates iptables mount kmod \
 && curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | gpg --dearmor -o /usr/share/keyrings/nvidia-ct.gpg \
 && curl -fsSL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
    | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-ct.gpg] https://#' > /etc/apt/sources.list.d/nvidia-ct.list \
 && apt-get update && apt-get install -y --no-install-recommends nvidia-container-toolkit \
 && rm -rf /var/lib/apt/lists/*
COPY --from=k3s /bin /opt/k3s/bin
# k3d's entrypoint execs /bin/k3s (Ubuntu: /bin -> /usr/bin)
RUN for t in k3s kubectl crictl ctr; do ln -sf /opt/k3s/bin/k3s /usr/bin/$t; done \
 # k3d's injected entrypoint uses `trap ... SIGTERM`, which dash rejects ("bad trap") -> restart loop
 && ln -sf bash /usr/bin/sh
ENV PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/opt/k3s/bin:/opt/k3s/bin/aux" \
    CRI_CONFIG_FILE=/var/lib/rancher/k3s/agent/etc/crictl.yaml
VOLUME /var/lib/kubelet /var/lib/rancher/k3s /var/lib/cni /var/log
ENTRYPOINT ["/opt/k3s/bin/k3s"]
CMD ["agent"]
