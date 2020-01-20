PYTHON ?= python
DIST_PYTHON ?= $(PYTHON)

NAME = receptor
IMAGE_NAME ?= $(NAME)
PIP_NAME = receptor
VERSION := $(shell $(DIST_PYTHON) setup.py --version)
ifeq ($(OFFICIAL),yes)
    RELEASE ?= 1
else
    ifeq ($(origin RELEASE), undefined)
        RELEASE := 0.git_$(shell git rev-parse --short HEAD)
    endif
endif
DIST ?= el7
ARCH ?= x86_64

NVR_RELEASE = $(RELEASE).$(DIST)
EPEL_DIST = $(subst el,epel-,$(DIST))
NVR = $(NAME)-$(VERSION)-$(NVR_RELEASE)
RESULTDIR = rpm-build/results-$(DIST)-$(ARCH)

.PHONY: clean version release dist sdist image dev shell test \
	mock-rpm mock-srpm image

clean:
	rm -rf dist
	rm -rf receptor.egg-info
	rm -rf rpm-build

version:
	@echo $(VERSION)

release:
	@echo $(RELEASE)

dist:
	$(DIST_PYTHON) setup.py bdist_wheel --universal

sdist: dist/$(NAME)-$(VERSION).tar.gz

dist/$(NAME)-$(VERSION).tar.gz: $(shell find receptor -type f -name '*.py')
	$(DIST_PYTHON) setup.py sdist

image: dist
	docker build --rm=true -t $(IMAGE_NAME) -f ./packaging/docker/Dockerfile .

dev:
	pip install -e .[dev]

shell:

test:
	tox

dist/$(VERSION).tar.gz: dist/$(NAME)-$(VERSION).tar.gz
	cp dist/$(NAME)-$(VERSION).tar.gz dist/$(VERSION).tar.gz

rpm-build/$(NVR).spec: packaging/rpm/$(NAME).spec.j2
	mkdir -p rpm-build
	ansible -i localhost, -c local all -m template	\
		-a "src=packaging/rpm/$(NAME).spec.j2 dest=rpm-build/$(NVR).spec" \
		-e version=$(VERSION) \
		-e release=$(NVR_RELEASE)

$(RESULTDIR)/$(NVR).src.rpm: dist/$(VERSION).tar.gz rpm-build/$(NVR).spec
	mock --buildsrpm --no-clean -r $(EPEL_DIST)-$(ARCH) --spec rpm-build/$(NVR).spec --sources dist/$(VERSION).tar.gz --resultdir $(RESULTDIR)

$(RESULTDIR)/$(NVR).rpm: $(RESULTDIR)/$(NVR).src.rpm
	mock --rebuild --no-clean -r $(EPEL_DIST)-$(ARCH) $(RESULTDIR)/$(NVR).src.rpm --resultdir $(RESULTDIR)
	@touch $@

mock-srpm: $(RESULTDIR)/$(NVR).src.rpm

mock-rpm: $(RESULTDIR)/$(NVR).rpm

