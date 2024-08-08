# syntax=docker/dockerfile:experimental
FROM quay.io/unstructured-io/base-images:rocky9.2-cpu-latest AS base

# NOTE: NB_USER ARG for mybinder.org compatibility:
# https://mybinder.readthedocs.io/en/latest/tutorials/dockerfile.html
ARG NB_USER=notebook-user
ARG NB_UID=1000
ARG PIP_VERSION
ARG PIPELINE_PACKAGE
ARG PYTHON_VERSION="3.11"

# Set up environment
ENV PYTHON python${PYTHON_VERSION}
ENV PIP ${PYTHON} -m pip
ENV HOME /home/${NB_USER}  # Define the HOME environment variable
ENV PYTHONPATH="${PYTHONPATH}:${HOME}"
ENV PATH="${HOME}/.local/bin:${PATH}"

# Create the user and home directory
RUN useradd -m -u ${NB_UID} ${NB_USER}

WORKDIR ${HOME}
USER ${NB_USER}

FROM base as python-deps

ARG NB_USER=notebook-user
ARG NB_UID=1000

COPY --chown=${NB_UID}:${NB_UID} requirements/base.txt requirements-base.txt
RUN ${PIP} install pip==${PIP_VERSION}
RUN ${PIP} install --no-cache -r requirements-base.txt

FROM python-deps as model-deps
RUN ${PYTHON} -c "import nltk; nltk.download('punkt')" && \
  ${PYTHON} -c "import nltk; nltk.download('averaged_perceptron_tagger')" && \
  ${PYTHON} -c "from unstructured.partition.model_init import initialize; initialize()"

FROM model-deps as code

ARG NB_USER=notebook-user
ARG NB_UID=1000

COPY --chown=${NB_UID}:${NB_UID} CHANGELOG.md CHANGELOG.md
COPY --chown=${NB_UID}:${NB_UID} logger_config.yaml logger_config.yaml
COPY --chown=${NB_UID}:${NB_UID} prepline_${PIPELINE_PACKAGE}/ prepline_${PIPELINE_PACKAGE}/
COPY --chown=${NB_UID}:${NB_UID} exploration-notebooks exploration-notebooks
COPY --chown=${NB_UID}:${NB_UID} scripts/app-start.sh scripts/app-start.sh

ENTRYPOINT ["scripts/app-start.sh"]
# Expose a default port of 8000. Note: The EXPOSE instruction does not actually publish the port,
# but some tooling will inspect containers and perform work contingent on networking support declared.
EXPOSE 8000
