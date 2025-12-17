# Changelog

## Backlog

- Add missing jsonld, RDF and SHACL
- Improve index search
- Centralise the data sources for index and predict_voc for ease of update/collaboration
- Quick index update testing
- Improve voc/rag tests (async/batch)
- Human feedback for rag tests to choose relevant metrics
- Implement client switch in tests
- Change model (some problem arose...)

## *14/05/2025*

## *30/04/2025*

- Added .ttl for OSLO vocabularies
- Added history to the tests
- Added scraped html documentation for SEMIC
  - Improved significantly 3 out of 4 context-based metrics
  - Did not change the other metrics
- Added baseline test, yielding pretty much zero on all metrics

## *26/03/2025*

- GitHub repos:
  - AI4Semantics
  - Indexation
- Indexation:
  - Built a new index to replace the old one
  - Semic:
    - rdf: almost every .ttl
    - shacl: every shacl.ttl
    - html: (locally) chunked documents
  - OSLO:
    - rdf: very few .jsonld (but rdflib extracts nothing or yields an error)
    - shacl: only one shacl.ttl
    - html: 5 pairs of Voc/AP, (remotely) scraped each concept from each page
- AI4Semantics
  - Allow for multiple clients in chatbot:
    - PwC internal API
    - Semic (needs to be tested for latest app version)
  - Vocabulary prediciton:
    - Can predict every semic and OSLO ***vocabulary*** present in the index
    - Extremely sensitive to prompt instructions and vocabulary description
  - Rag:
    - semic html improved some results, but no uri in the docs
    - sometimes fails to retrieve any relevant documents for OSLO
  - Tests:
    - 35 questions: 6 for semic, 29 for OSLO
    - Added test for vocabulary prediction
    - More questions for rag yield more stable averaged results
    - Cannot decide between semic and OSLO (e.g. mixes thoroughfare and straatnaam)

## *12/03/2025*

- Switched to new [PwC internal API](<https://genai-sharedservice-emea.pwcinternal.com>)
  - Should work from anywhere
  - Tokens not needed anymore
  - Improved latency
- Basic test workflow set up (using [ragas](https://docs.ragas.io/en/stable/))
  - Not deterministic
  - Ok for extreme cases
- Can predict OSLO vocabulary
  - Perfectly bilingual
    - predicts vocabulary disregarding description/prompt language discrepancy
    - is it good or bad? The tests questions may not be specific enough to choose

## *26/02/2025*

- Switched to internal PwC API
  - Should work from anywhere
  - Automated tokens system
- RAG workflow finalised
  - RAG done 'manually'
    1. predict vocabulary
    2. search documents index
    3. generate response
