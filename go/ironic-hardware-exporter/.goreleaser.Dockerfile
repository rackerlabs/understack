FROM gcr.io/distroless/base-debian12:nonroot
COPY --chmod=555 ironic-hardware-exporter /usr/local/bin/ironic-hardware-exporter
USER 65532:65532
ENTRYPOINT ["/usr/local/bin/ironic-hardware-exporter"]
