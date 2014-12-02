Name:           copr-java
Version:        0.2
Release:        1%{?dist}
Summary:        COPR Java client
License:        ASL 2.0
URL:            https://fedorahosted.org/copr/

# Source is created by
# git clone https://git.fedorahosted.org/git/copr.git
# cd copr/java
# tito build --tgz
Source0:        %{name}-%{version}.tar.gz

BuildRequires:  maven-local
BuildRequires:  mvn(com.beust:jcommander)
BuildRequires:  mvn(com.google.code.gson:gson)
BuildRequires:  mvn(junit:junit)
BuildRequires:  mvn(org.apache.felix:maven-bundle-plugin)
BuildRequires:  mvn(org.apache.httpcomponents:httpclient)
BuildRequires:  mvn(org.apache.httpcomponents:httpclient::tests:)
BuildRequires:  mvn(org.easymock:easymock)
BuildRequires:  mvn(org.ini4j:ini4j)

%description
COPR is lightweight build system. It allows you to create new project in WebUI,
and submit new builds and COPR will create yum repository from latest builds.

This package contains Java client library.

%package javadoc
Summary:        API documentation for %{name}

%description javadoc
This package provides %{summary}.

%prep
%setup -q

%build
%mvn_build

%install
%mvn_install

%files -f .mfiles
%doc LICENSE NOTICE

%files javadoc -f .mfiles-javadoc
%doc LICENSE NOTICE

%changelog
* Tue Sep 16 2014 Mikolaj Izdebski <mizdebsk@redhat.com>
- Initial packaging
