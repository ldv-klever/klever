FROM cif:latest

# Install dependencies and prepare environment.
RUN apt-get update && \
    apt-get install -y python3

# Copy Psi source code that is executable code as well.
COPY bin/psi /bin/psi
COPY psi /psi

# Create and move to working directory.
VOLUME /work
WORKDIR /work

