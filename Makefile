#############################################################################
# File		: Makefile
# Package	: virt-bridge-setup
#############################################################################

NAME=virt-bridge-setup
PREFIX=/usr
SBINDIR=$(PREFIX)/sbin
ETCSYSNETDIR=/etc/systemd/network
OSCDIR=/home/aginies/aginies_obs/Virtualization/$(NAME)

PACKAGE=$(NAME)
FILES=LICENSE Makefile README.md virt-bridge-setup.py 98-default-bridge.link
VERSION=$(shell grep -m 1 '^Version:' $(NAME).spec | awk '{print $$2}')

all: 	cleandist clean

clean: 	
	rm -rf *~

copy:
	cp -avf $(NAME).changes $(NAME).spec $(OSCDIR)

version: 
	@echo $(VERSION)

install: 
	mkdir -p $(DESTDIR)$(SBINDIR)
	mkdir -p $(DESTDIR)$(ETCSYSNETDIR)
	cp -av $(NAME).py $(DESTDIR)$(SBINDIR)/$(NAME)
	cp -av 98-default-bridge.link $(DESTDIR)/$(ETCSYSNETDIR)

cleandist:
	rm -rf $(PACKAGE)-$(VERSION) $(PACKAGE)-$(VERSION).tar.bz2

tar:	cleandist clean
	mkdir $(PACKAGE)-$(VERSION)
	cp -av $(FILES) $(PACKAGE)-$(VERSION)
	tar cvfj $(PACKAGE)-$(VERSION).tar.bz2 $(PACKAGE)-$(VERSION)
	rm -rf $(PACKAGE)-$(VERSION)
