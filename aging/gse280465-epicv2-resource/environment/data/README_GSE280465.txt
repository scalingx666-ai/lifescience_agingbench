GSE280465 Bioconductor ExperimentHub resource
==============================================

This Zenodo deposit contains a processed DNA methylation resource derived
from GEO Series GSE280465 through a Bioconductor ExperimentHub data package.

Source study
------------

GEO accession: https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE280465
Publication DOI: https://doi.org/10.1111/acel.14451
PubMed: https://pubmed.ncbi.nlm.nih.gov/39780748/

Apsley AT, Ye Q, Caspi A, Chiaro C, Etzel L, Hastings WJ, Heim CM, Kozlosky J, Noll JG, Schreier HMC, Shenk CE, Sugden K, Shalev I. Cross-tissue comparison of epigenetic aging clocks in humans. Aging Cell. 2025;24(4):e14451.

Resource file
-------------

GSE280465_GPL33022_EPICv2.rds
- Class: RangedSummarizedExperiment
- Platform: GPL33022
- Array: Illumina Infinium MethylationEPIC version 2
- Genome: hg38
- Dimensions: 930075 CpG loci x 163 samples
- Subjects: 47
- Tissues: Buccal: 46, PBMC: 45, Saliva: 37, DBS: 35
- Assays: beta, M, CN

Data processing
---------------

The RDS file was generated from a minfi GenomicRatioSet object and
converted to a RangedSummarizedExperiment object. The object contains
methylation beta values, M values, copy number estimates, genomic ranges,
sample-level phenotype metadata, and provenance metadata.

Checksums
---------

SHA256 checksums are provided in the file named:
checksums

Notes for reuse
---------------

This file is a derived resource intended for Bioconductor workflows. Users
should cite the original GSE280465 publication, the GEO accession, this
Zenodo record, and the Bioconductor package that provides ExperimentHub
access.
