# What is UnderStack?

UnderStack is a collection of open-source tools and technologies that provides
flexible, scalable, and cost-effective infrastructure management solution. The
focus is on deploying bare metal in data centers with functional DCIM and IPAM.

## About the Guide

While the deployment of UnderStack leans heavily into [GitOps][gitops], it is not meant to
be a definitive guide to [GitOps][gitops]. It is also not the only way GitOps can be used
with UnderStack but instead focuses on one example deployment installation.
It will make a few assumptions and some opinionated choices that may not align
with a production best practices installation. Improvements are always welcome.

## System Division

A fully deployed UnderStack is divided into three distinct parts, or clusters,
that are referred to in the documentation as:

- Management
- Global
- Site(s)

```mermaid
flowchart TD

  A[Management] mb@--> B[Global];
  A mc@--> C[Site A];
  A md@--> D[Site B...];
  A me@--> E[Site N];

  subgraph P[Partition]
    B <==> C;
    B <==> D;
    B <==> E;
  end

  %% Style the subgraph with dashed border
  style P stroke-dasharray: 5 5

  classDef animate stroke-dasharray: 9,5,stroke-dashoffset: 900,animation: dash 25s linear infinite;
  class mb animate
  class mc animate
  class md animate
  class me animate
```

A fully functioning system only needs one _Management_ cluster, one _Global_
cluster and one or more _Site_ cluster(s). In this configuration,
the _Management_ cluster is responsible for utilizing our [GitOps][gitops]
tool, [ArgoCD][argocd] to deploy the expected state to all other clusters
and provide other observation and monitoring services like logging and alerting.

While the _Global_ cluster is
responsible for hosting any services that are expected to exist only once
for a partition such as the DCIM/IPAM tool. While the _Site_
clusters will run the tools and services that need to live close to the
actual hardware.

In fact, one _Management_ cluster can control multiple _Global_ clusters
and their associated _Site_ clusters. We call the grouping of the _Global_
cluster and it's associated _Site_ clusters a _partition_. An example
would be a staging partition and a production partition.

```mermaid
flowchart TD

  A[Management] mb@--> B[Global];
  A mc@--> C[Site A];
  A md@--> D[Site B...];
  A me@--> E[Site N];
  A mf@--> F[Global];
  A mg@--> G[Site D];
  A mh@--> H[Site E...];
  A mi@--> I[Site Z];

  subgraph S[Partition staging]
    B <==> C;
    B <==> D;
    B <==> E;
  end

  subgraph P[Partition production]
    F <==> G;
    F <==> H;
    F <==> I;
  end

  %% Style both subgraphs with dashed borders
  style S stroke-dasharray: 5 5
  style P stroke-dasharray: 5 5

  classDef animate stroke-dasharray: 9,5,stroke-dashoffset: 900,animation: dash 25s linear infinite;
  class mb animate
  class mc animate
  class md animate
  class me animate
  class mf animate
  class mg animate
  class mh animate
  class mi animate
```

[argocd]: <https://argo-cd.readthedocs.io/en/stable/>
[gitops]: <https://about.gitlab.com/topics/gitops/>
