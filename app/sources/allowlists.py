"""Curated allowlists and blocklists for source credibility scoring."""

from __future__ import annotations

# Layer 1: IFCN-certified and recognized fact-checking organizations
FACT_CHECKERS: set[str] = {
    # India
    "boomlive.in",
    "altnews.in",
    "factly.in",
    "newschecker.in",
    "thequint.com",
    "factcheck.afp.com",
    "pib.gov.in",
    "pibfactcheck.in",
    # Global
    "snopes.com",
    "politifact.com",
    "factcheck.org",
    "fullfact.org",
    "reuters.com/fact-check",
    "apnews.com/hub/ap-fact-check",
    "bbc.com/news/reality_check",
    "washingtonpost.com/news/fact-checker",
}

# Layer 2: Official / primary sources by category
OFFICIAL_DOMAINS: dict[str, set[str]] = {
    "government_india": {
        "india.gov.in",
        "pib.gov.in",
        "mha.gov.in",
        "mof.gov.in",
        "meity.gov.in",
        "nic.in",
    },
    "finance_india": {
        "rbi.org.in",
        "sebi.gov.in",
        "irdai.gov.in",
        "incometaxindia.gov.in",
        "gst.gov.in",
    },
    "health_india": {
        "icmr.gov.in",
        "aiims.edu",
        "mohfw.gov.in",
        "nhp.gov.in",
        "cdsco.gov.in",
    },
    "science_india": {
        "isro.gov.in",
        "dst.gov.in",
        "imd.gov.in",
    },
    "government_global": {
        "who.int",
        "un.org",
        "cdc.gov",
        "nih.gov",
        "nasa.gov",
        "fda.gov",
        "europa.eu",
    },
    "academic": {
        "pubmed.ncbi.nlm.nih.gov",
        "scholar.google.com",
        "nature.com",
        "thelancet.com",
        "bmj.com",
        "science.org",
        "nejm.org",
    },
}

ALL_OFFICIAL_DOMAINS: set[str] = set()
for _domains in OFFICIAL_DOMAINS.values():
    ALL_OFFICIAL_DOMAINS.update(_domains)

# Layer 3: Established news outlets with editorial standards
NEWS_OUTLETS: dict[str, set[str]] = {
    "india": {
        "ndtv.com",
        "thehindu.com",
        "indianexpress.com",
        "timesofindia.indiatimes.com",
        "hindustantimes.com",
        "thewire.in",
        "scroll.in",
        "livemint.com",
        "economictimes.indiatimes.com",
        "bbc.com/hindi",
        "news18.com",
        "deccanherald.com",
        "theprint.in",
        "firstpost.com",
    },
    "global": {
        "reuters.com",
        "apnews.com",
        "bbc.com",
        "bbc.co.uk",
        "theguardian.com",
        "nytimes.com",
        "washingtonpost.com",
        "aljazeera.com",
        "dw.com",
        "france24.com",
        "edition.cnn.com",
    },
    "science_health": {
        "nature.com",
        "thelancet.com",
        "bmj.com",
        "science.org",
        "webmd.com",
        "mayoclinic.org",
        "health.harvard.edu",
        "who.int/news",
        "sciencedaily.com",
    },
}

ALL_NEWS_DOMAINS: set[str] = set()
for _domains in NEWS_OUTLETS.values():
    ALL_NEWS_DOMAINS.update(_domains)

# Known unreliable / content farm domains (blocklist)
BLOCKED_DOMAINS: set[str] = {
    "beforeitsnews.com",
    "naturalnews.com",
    "infowars.com",
    "worldnewsdailyreport.com",
    "yournewswire.com",
    "neonnettle.com",
    "thehealthranger.com",
    "dailybuzzlive.com",
    "empire-news.net",
    "huzlers.com",
    "newswatch33.com",
    "react365.com",
    "thereisnews.com",
    "breakingnews365.net",
}

# Sensationalist language patterns (signals low credibility)
SENSATIONALIST_PATTERNS: list[str] = [
    "SHOCKING",
    "They don't want you to know",
    "EXPOSED",
    "BREAKING",
    "Share before deleted",
    "Forward to everyone",
    "Urgent!!!",
    "100% proven",
    "Doctors hate this",
    "Big pharma",
    "Government hiding",
    "Wake up people",
    "EXPOSED",
    "BANNED",
]
