# Build iPXE separately to avoid rebuilding on every Ironic change
FROM docker.io/debian:trixie-20260421 AS ipxe-builder

# example --build-arg IPXE_FLAGS="DEBUG=tcp:3,xfer:3,netdevice:2,ipv4:2,httpcore:2,httpconn:2"
ARG IPXE_FLAGS=""

RUN apt-get update && apt-get install -y git build-essential bison flex libssl-dev && mkdir /src
WORKDIR /src

RUN git clone https://github.com/ipxe/ipxe.git
WORKDIR /src/ipxe
# renovate: name=ipxe/ipxe repo=https://github.com/ipxe/ipxe.git branch=master
ARG IPXE_GIT_REF=75115ee998df9345eb9475aeb444ce9b01fca264
RUN git checkout ${IPXE_GIT_REF}

# Copy config files
COPY ipxe-general.h /src/ipxe/src/config/local/general.h
COPY ipxe-branding.h /src/ipxe/src/config/local/branding.h

WORKDIR /src/ipxe/src
RUN make bin-x86_64-efi/snponly.efi ${IPXE_FLAGS}

# Final stage with just the binary
FROM scratch AS ipxe-artifact
COPY --from=ipxe-builder /src/ipxe/src/bin-x86_64-efi/snponly.efi /snponly.efi
