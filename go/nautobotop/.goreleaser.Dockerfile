# goreleaser is making the binary dynamically linked so can't use the static container
FROM gcr.io/distroless/base-debian12:nonroot
COPY --chmod=555 nautobotop /usr/local/bin/nautobotop
USER 65532:65532
ENTRYPOINT ["/usr/local/bin/nautobotop"]
