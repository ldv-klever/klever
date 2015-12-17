FROM cif:latest

# Install dependencies and prepare environment.
RUN apt-get update && \
    apt-get install -y python3

# Copy Klever Core source code that is executable code as well.
COPY bin/klever-core /bin/klever-core
COPY core /core

# Create and move to working directory.
VOLUME /work
WORKDIR /work

