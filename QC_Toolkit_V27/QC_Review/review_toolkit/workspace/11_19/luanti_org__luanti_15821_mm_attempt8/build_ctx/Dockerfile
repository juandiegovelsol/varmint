FROM luanti15821:base
# QC image: same apt/clone/cmake layers as the CB Dockerfile (cached base built from it at the base commit,
# no bugs), then the Attempt8 injected bugs + harbor_base snapshot + incremental build + Attempt8 asset.
COPY bugs/ /tmp/bugs/
RUN set -e; cd /app; for p in /tmp/bugs/*.patch; do git -C /app apply "$p" || patch -p1 -d /app < "$p"; done; rm -rf /tmp/bugs
RUN rm -rf /app/.git && git -C /app init -q && git -C /app -c user.email=h@l -c user.name=h add -A \
 && git -C /app -c user.email=h@l -c user.name=h commit -q -m base && git -C /app tag harbor_base
RUN cmake --build /app/build --parallel "$(nproc)"
RUN rm -rf /app/.harbor_assets && mkdir -p /logs /app/.harbor_assets
COPY recording.mp4 /app/.harbor_assets/
CMD ["bash"]
