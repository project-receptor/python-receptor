PYTHON ?= python
ifeq ($(origin VIRTUAL_ENV), undefined)
    DIST_PYTHON ?= pipenv run $(PYTHON)
else
    DIST_PYTHON ?= $(PYTHON)
endif

NAME = receptor
IMAGE_NAME ?= $(NAME)
PIP_NAME = receptor
VERSION := $(shell $(DIST_PYTHON) setup.py --version)
ifeq ($(OFFICIAL),yes)
    RELEASE ?= 1
else
    ifeq ($(origin RELEASE), undefined)
        RELEASE := 0.git$(shell date -u +%Y%m%d%H%M).$(shell git rev-parse --short HEAD)
    endif
endif

.PHONY: dist sdist test

clean:
	rm -rf dist
	rm -rf receptor.egg-info

dist:
	$(DIST_PYTHON) setup.py bdist_wheel --universal

sdist: dist/$(NAME)-$(VERSION).tar.gz

dist/$(NAME)-$(VERSION).tar.gz:
	$(DIST_PYTHON) setup.py sdist

image: dist
	docker build --rm=true -t $(IMAGE_NAME) -f ./packaging/docker/Dockerfile .

dev:
	pipenv install

shell:
	pipenv shell

test:
	tox
