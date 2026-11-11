@echo off
:: =============================================================================
:: run_full_suite.bat — Full integration test matrix
::
:: Runs 12 targeted test suites covering CocoIndex and Flexible GraphRAG backends.
::
:: Usage (from repo root):
::   tests\integration\run_full_suite.bat                        — run all 12 suites
::   tests\integration\run_full_suite.bat <step>                 — run one suite by number
::   tests\integration\run_full_suite.bat coco                   — run all 3 CocoIndex native suites
::   tests\integration\run_full_suite.bat flex                   — run all 9 Flexible suites (default pipeline)
::   tests\integration\run_full_suite.bat coco-flex              — flex 4-12 with PIPELINE_BACKEND=cocoindex
::   tests\integration\run_full_suite.bat flex --pipeline cocoindex  — same as coco-flex
::   tests\integration\run_full_suite.bat langflow               — run flex 1-9 with LangFlow UI enabled
::   tests\integration\run_full_suite.bat <step> --langflow true — add LangFlow UI to any flex step(s)
::
:: Steps:
::   1  [coco 1] CocoIndex native data sources (filesystem,s3,azure_blob,google_drive)
::   2  [coco 2] CocoIndex native PG graphs (neo4j, falkordb, surrealdb)
::   3  [coco 3] CocoIndex native vector stores (qdrant, lancedb, postgres)
::   4  [flex 1] Flexible data sources (14 sources)  [--clean between each source]
::   5  [flex 2] Flexible LI PG graphs (neo4j,falkordb,memgraph,arcadedb,nebula,ladybug) + qdrant  [LI chunker]
::       (spanner commented out — cloud trial expired; restore when available)
::   6  [flex 3] Flexible LC PG graphs (neo4j,arangodb,apache_age,hugegraph,surrealdb,tigergraph,arcadedb,falkordb,memgraph,nebula,cosmos_gremlin) + qdrant  [LI chunker]
::   7  [flex 4] Flexible vector stores  (qdrant,lancedb,postgres,chroma,milvus,weaviate,elasticsearch,opensearch,pinecone,neo4j)  [LI chunker]
::   8  [flex 5] Flexible search engines (elasticsearch,opensearch,bm25)  [LI chunker]
::   9  [flex 6] Flexible RDF stores (fuseki,oxigraph,graphdb)  [LI chunker]
::  10  [flex 7] Flexible LC PG graphs (neo4j,falkordb,memgraph,arcadedb,nebula,ladybug) + qdrant  [LC chunker, graph_backend=langchain]
::  11  [flex 8] Flexible LC search engines (elasticsearch,opensearch,bm25)  [LC chunker, search_backend=langchain]
::  12  [flex 9] Flexible LC vector stores (qdrant,lancedb,postgres,chroma,milvus,weaviate,elasticsearch,opensearch,pinecone,neo4j)  [LC chunker, vector_backend=langchain]
::
:: LangFlow flag (--langflow true):
::   Appends --langflow true to every flex step (4-12), enabling LangFlow UI component tests.
::   The 'langflow' step alias is a shorthand for  flex --langflow true.
::   CocoIndex steps (1-3) are never affected — LangFlow is a flexible-pipeline feature.
::
:: Pipeline flag (--pipeline cocoindex):
::   Appends --pipeline cocoindex to every flex step (4-12). Same flexible sources/targets
::   and same tests as default flex — only the orchestrator changes (CocoIndex coco.App).
::   Alias: coco-flex  (= flex --pipeline cocoindex).
::   Native coco steps (1-3) already set --pipeline cocoindex; this flag does not change them.
::   Mutually exclusive with --langflow true (LangFlow + CocoIndex pipeline cannot both run).
::
:: Prerequisites:
::   - .env configured with API keys and DB connection strings
::   - Docker containers running  (qdrant, elasticsearch, neo4j, falkordb, etc.)
::   - Virtual env activated:  venv-3.14\Scripts\activate
::
:: Chunker policy:
::   CocoIndex suites       → chunker=cocoindex (uses CocoIndex's own splitting pipeline)
::   Flexible suites 1-6    → chunker=llamaindex (LlamaIndex SentenceSplitter, stable default)
::   Flexible suites 7-9    → chunker=langchain  (LangChain splitter, LC pipeline)
::
:: Note on --backends: used by run_matrix.py internally to set all individual backend
::   env vars (GRAPH_BACKEND, VECTOR_BACKEND, SEARCH_BACKEND) at once.  It is NOT a
::   real flexible-graphrag config key; individual overrides (--graph-backend, etc.)
::   appear in the job label instead.
::
:: --clean (cleanup.py before each backend combination) is set on all suites
:: where data from one job could pollute the next (multiple backends in sequence).
:: =============================================================================

setlocal enabledelayedexpansion

set MATRIX=uv run tests/integration/run_matrix.py
set PASS=0
set FAIL=0

:: Parse step argument (empty = all)
set STEP=%~1
if "%STEP%"=="" set STEP=all

:: Parse optional flags (any position after the step)
set LANGFLOW_FLAG=
set CLOUD_PG=
set PIPELINE_FLAG=
:parse_args
shift
if "%~1"=="" goto args_done
if /I "%~1"=="--langflow" (
    if /I "%~2"=="true" (
        set LANGFLOW_FLAG=--langflow true
        shift
    )
)
if /I "%~1"=="--cloud" (
    if not "%~2"=="" (
        set CLOUD_PG=,%~2
        shift
    )
)
if /I "%~1"=="--pipeline" (
    if /I "%~2"=="cocoindex" (
        set PIPELINE_FLAG=--pipeline cocoindex
        shift
    )
)
goto parse_args
:args_done

:: 'langflow' step alias = flex steps 4-12 with --langflow true
if /I "%STEP%"=="langflow" (
    set STEP=flex
    if "%LANGFLOW_FLAG%"=="" set LANGFLOW_FLAG=--langflow true
)

:: 'coco-flex' step alias = flex steps 4-12 with --pipeline cocoindex
if /I "%STEP%"=="coco-flex" (
    set STEP=flex
    if "%PIPELINE_FLAG%"=="" set PIPELINE_FLAG=--pipeline cocoindex
)

:: LangFlow + CocoIndex pipeline are mutually exclusive
if not "%LANGFLOW_FLAG%"=="" if not "%PIPELINE_FLAG%"=="" (
    echo.
    echo ERROR: --langflow true and --pipeline cocoindex cannot be combined.
    echo        LangFlow and the CocoIndex pipeline are mutually exclusive.
    exit /b 1
)

:: ── Check step argument validity
if /I not "%STEP%"=="all" ^
if /I not "%STEP%"=="coco" ^
if /I not "%STEP%"=="flex" ^
if not "%STEP%"=="1" ^
if not "%STEP%"=="2" ^
if not "%STEP%"=="3" ^
if not "%STEP%"=="4" ^
if not "%STEP%"=="5" ^
if not "%STEP%"=="6" ^
if not "%STEP%"=="7" ^
if not "%STEP%"=="8" ^
if not "%STEP%"=="9" ^
if not "%STEP%"=="10" ^
if not "%STEP%"=="11" ^
if not "%STEP%"=="12" (
    echo.
    echo ERROR: Invalid step %STEP%.
    echo Usage: run_full_suite.bat [1-12 ^| coco ^| flex ^| coco-flex ^| langflow ^| all] [--pipeline cocoindex] [--langflow true] [--cloud spanner,...]
    echo.
    echo Steps:
    echo   1  [coco 1] CocoIndex native data sources
    echo   2  [coco 2] CocoIndex native PG graphs
    echo   3  [coco 3] CocoIndex native vector stores
    echo   4  [flex 1] Flexible data sources ^(14 sources^)
    echo   5  [flex 2] Flexible LI PG graphs               [LI chunker]
    echo   6  [flex 3] Flexible LC PG graphs               [LI chunker]
    echo   7  [flex 4] Flexible vector stores              [LI chunker]
    echo   8  [flex 5] Flexible search engines             [LI chunker]
    echo   9  [flex 6] Flexible RDF stores                 [LI chunker]
    echo  10  [flex 7] Flexible LC PG graphs               [LC chunker, graph_backend=langchain]
    echo  11  [flex 8] Flexible LC search engines          [LC chunker, search_backend=langchain]
    echo  12  [flex 9] Flexible LC vector stores           [LC chunker, vector_backend=langchain]
    echo.
    echo  coco-flex — alias for flex --pipeline cocoindex ^(steps 4-12 under CocoIndex pipeline^)
    echo  langflow  — alias for flex with --langflow true ^(steps 4-12^)
    exit /b 1
)

:: ── Determine which groups to run
set RUN_COCO=0
set RUN_FLEX=0
if /I "%STEP%"=="all"  ( set RUN_COCO=1 & set RUN_FLEX=1 )
if /I "%STEP%"=="coco" ( set RUN_COCO=1 )
if /I "%STEP%"=="flex" ( set RUN_FLEX=1 )
if "%STEP%"=="1"  set RUN_COCO=1
if "%STEP%"=="2"  set RUN_COCO=1
if "%STEP%"=="3"  set RUN_COCO=1
if "%STEP%"=="4"  set RUN_FLEX=1
if "%STEP%"=="5"  set RUN_FLEX=1
if "%STEP%"=="6"  set RUN_FLEX=1
if "%STEP%"=="7"  set RUN_FLEX=1
if "%STEP%"=="8"  set RUN_FLEX=1
if "%STEP%"=="9"  set RUN_FLEX=1
if "%STEP%"=="10" set RUN_FLEX=1
if "%STEP%"=="11" set RUN_FLEX=1
if "%STEP%"=="12" set RUN_FLEX=1

:: =============================================================================
:: COCOINDEX PIPELINE TESTS  (steps 1-3)
:: =============================================================================

if "%RUN_COCO%"=="1" (
    echo.
    echo ============================================================
    echo  COCOINDEX PIPELINE TESTS
    echo ============================================================
)

:: ── [coco 1/3] Native data sources
::   One job per source; per-job test filter restricts test_cocoindex.py:
::     filesystem  → full suite  (upload path fully exercised)
::     s3 / azure_blob / google_drive → smoke + source-reporting only
::   Cloud sources skip file-upload tests when credentials are absent.
::   Configure S3_CONFIG / AZURE_BLOB_CONFIG / GOOGLE_DRIVE_CONFIG in .env
::   to exercise them end-to-end.
if "%STEP%"=="all" set DO_S1=1
if "%STEP%"=="coco" set DO_S1=1
if "%STEP%"=="1"   set DO_S1=1
if defined DO_S1 (
    echo.
    echo [coco 1/3] CocoIndex native data sources ^(filesystem,s3,azure_blob,google_drive^) + qdrant + ES  [--clean] [chunker:cocoindex]
    %MATRIX% --vector qdrant --search elasticsearch ^
             --pipeline cocoindex --source-backend cocoindex ^
             --graph-backend cocoindex --vector-backend cocoindex ^
             --chunker cocoindex ^
             --data-source all --clean
    if !ERRORLEVEL! EQU 0 ( set /a PASS+=1 ) else ( set /a FAIL+=1 )
)

:: ── [coco 2/3] Native PG graphs
if "%STEP%"=="all" set DO_S2=1
if "%STEP%"=="coco" set DO_S2=1
if "%STEP%"=="2"   set DO_S2=1
if defined DO_S2 (
    echo.
    echo [coco 2/3] CocoIndex native PG graphs ^(neo4j, falkordb, surrealdb^) + qdrant  [--clean] [chunker:cocoindex]
    %MATRIX% --pg neo4j,falkordb,surrealdb --vector qdrant --search elasticsearch ^
             --pipeline cocoindex ^
             --graph-backend cocoindex --vector-backend cocoindex ^
             --chunker cocoindex ^
             --clean
    if !ERRORLEVEL! EQU 0 ( set /a PASS+=1 ) else ( set /a FAIL+=1 )
)

:: ── [coco 3/3] Native vector stores
if "%STEP%"=="all" set DO_S3=1
if "%STEP%"=="coco" set DO_S3=1
if "%STEP%"=="3"   set DO_S3=1
if defined DO_S3 (
    echo.
    echo [coco 3/3] CocoIndex native vector stores ^(qdrant, lancedb, postgres^)  [--clean] [chunker:cocoindex]
    %MATRIX% --vector qdrant,lancedb,postgres ^
             --pipeline cocoindex ^
             --graph-backend cocoindex --vector-backend cocoindex ^
             --chunker cocoindex ^
             --clean
    if !ERRORLEVEL! EQU 0 ( set /a PASS+=1 ) else ( set /a FAIL+=1 )
)

:: =============================================================================
:: FLEXIBLE GRAPHRAG PIPELINE TESTS  (steps 4-12)
:: =============================================================================

if "%RUN_FLEX%"=="1" (
    echo.
    echo ============================================================
    echo  FLEXIBLE GRAPHRAG PIPELINE TESTS
    echo ============================================================
)

:: ── [flex 1/9] Flexible data sources  (one job per source, 14 total)
::   Each job runs exactly the test matching its data source name.
::   No --pg → ENABLE_KNOWLEDGE_GRAPH=false (fast, no KG extraction)
if "%STEP%"=="all" set DO_S4=1
if "%STEP%"=="flex" set DO_S4=1
if "%STEP%"=="4"   set DO_S4=1
if defined DO_S4 (
    echo.
    echo [flex 1/9] Flexible data sources ^(14 sources^) + qdrant + ES  [--clean] [chunker:llamaindex] %LANGFLOW_FLAG% %PIPELINE_FLAG%
    %MATRIX% --vector qdrant --search elasticsearch ^
             --data-source filesystem,web,wikipedia,youtube,alfresco,nuxeo,cmis,s3,box,azure_blob,onedrive,sharepoint,google_drive,gcs ^
             --backends llamaindex ^
             --chunker llamaindex ^
             --clean %LANGFLOW_FLAG% %PIPELINE_FLAG%
    if !ERRORLEVEL! EQU 0 ( set /a PASS+=1 ) else ( set /a FAIL+=1 )
)

:: ── [flex 2/9] Flexible LI PG graphs  (LlamaIndex backend — local stores)
::   ladybug is embedded (no Docker container needed).
::   cloud stores (spanner, neptune, neptune_analytics) only with --cloud (off by default).
if "%STEP%"=="all" set DO_S5=1
if "%STEP%"=="flex" set DO_S5=1
if "%STEP%"=="5"   set DO_S5=1
if defined DO_S5 (
    echo.
    echo [flex 2/9] Flexible LI PG graphs ^(neo4j,falkordb,memgraph,arcadedb,nebula,ladybug%CLOUD_PG%^) + qdrant  [--clean] [chunker:llamaindex] %LANGFLOW_FLAG% %PIPELINE_FLAG%
    %MATRIX% --pg neo4j,falkordb,memgraph,arcadedb,nebula,ladybug%CLOUD_PG% --vector qdrant ^
             --graph-backend llamaindex ^
             --chunker llamaindex ^
             --clean %LANGFLOW_FLAG% %PIPELINE_FLAG%
    if !ERRORLEVEL! EQU 0 ( set /a PASS+=1 ) else ( set /a FAIL+=1 )
)

:: ── [flex 3/9] Flexible LC PG graphs  (LangChain backend — 11 stores)
::   cosmos_gremlin uses local TinkerPop Gremlin Server (port 8182) as Cosmos substitute.
::   All stores have Docker containers running (docker-compose.yaml).
if "%STEP%"=="all" set DO_S6=1
if "%STEP%"=="flex" set DO_S6=1
if "%STEP%"=="6"   set DO_S6=1
if defined DO_S6 (
    echo.
    echo [flex 3/9] Flexible LC PG graphs ^(neo4j,arangodb,apache_age,hugegraph,surrealdb,tigergraph,arcadedb,falkordb,memgraph,nebula,cosmos_gremlin%CLOUD_PG%^) + qdrant  [--clean] [chunker:llamaindex] %LANGFLOW_FLAG% %PIPELINE_FLAG%
    %MATRIX% --pg neo4j,arangodb,apache_age,hugegraph,surrealdb,tigergraph,arcadedb,falkordb,memgraph,nebula,cosmos_gremlin%CLOUD_PG% ^
             --vector qdrant ^
             --graph-backend langchain ^
             --chunker llamaindex ^
             --clean %LANGFLOW_FLAG% %PIPELINE_FLAG%
    if !ERRORLEVEL! EQU 0 ( set /a PASS+=1 ) else ( set /a FAIL+=1 )
)

:: ── [flex 4/9] Flexible vector stores  (LlamaIndex backend — 10 stores)
::   No --pg → ENABLE_KNOWLEDGE_GRAPH=false
::   milvus / weaviate / lancedb / pinecone use langchain vector backend automatically.
::   neo4j here = vector-only (no graph); pinecone uses cloud Pinecone from .env.
if "%STEP%"=="all" set DO_S7=1
if "%STEP%"=="flex" set DO_S7=1
if "%STEP%"=="7"   set DO_S7=1
if defined DO_S7 (
    echo.
    echo [flex 4/9] Flexible vector stores ^(qdrant,lancedb,postgres,chroma,milvus,weaviate,elasticsearch,opensearch,pinecone,neo4j^)  [--clean] [chunker:llamaindex] %LANGFLOW_FLAG% %PIPELINE_FLAG%
    %MATRIX% --vector qdrant,lancedb,postgres,chroma,milvus,weaviate,elasticsearch,opensearch,pinecone,neo4j ^
             --vector-backend llamaindex ^
             --chunker llamaindex ^
             --clean %LANGFLOW_FLAG% %PIPELINE_FLAG%
    if !ERRORLEVEL! EQU 0 ( set /a PASS+=1 ) else ( set /a FAIL+=1 )
)

:: ── [flex 5/9] Flexible search engines  (LlamaIndex backend)
::   No --pg → ENABLE_KNOWLEDGE_GRAPH=false
if "%STEP%"=="all" set DO_S8=1
if "%STEP%"=="flex" set DO_S8=1
if "%STEP%"=="8"   set DO_S8=1
if defined DO_S8 (
    echo.
    echo [flex 5/9] Flexible LI search engines + qdrant  [--clean] [chunker:llamaindex] %LANGFLOW_FLAG% %PIPELINE_FLAG%
    %MATRIX% --vector qdrant --search elasticsearch,opensearch,bm25 ^
             --search-backend llamaindex ^
             --chunker llamaindex ^
             --clean %LANGFLOW_FLAG% %PIPELINE_FLAG%
    if !ERRORLEVEL! EQU 0 ( set /a PASS+=1 ) else ( set /a FAIL+=1 )
)

:: ── [flex 6/9] Flexible RDF stores + qdrant
::   No --pg (RDF suite tests RDF stores, not property graphs)
if "%STEP%"=="all" set DO_S9=1
if "%STEP%"=="flex" set DO_S9=1
if "%STEP%"=="9"   set DO_S9=1
if defined DO_S9 (
    echo.
    echo [flex 6/9] Flexible RDF stores + qdrant  [--clean] [chunker:llamaindex] %LANGFLOW_FLAG% %PIPELINE_FLAG%
    %MATRIX% --vector qdrant --rdf fuseki,oxigraph,graphdb ^
             --backends llamaindex ^
             --chunker llamaindex ^
             --clean %LANGFLOW_FLAG% %PIPELINE_FLAG%
    if !ERRORLEVEL! EQU 0 ( set /a PASS+=1 ) else ( set /a FAIL+=1 )
)

:: ── [flex 7/9] Flexible LC PG graphs (LI stores) + LC chunker
::   LI graph stores (neo4j,falkordb,memgraph,arcadedb,nebula,ladybug) tested with
::   graph-backend=langchain and LC chunker — the truly separate LangChain adapter path.
::   Complements flex 3/9 which tests LC-only stores (arangodb, hugegraph, etc.).
if "%STEP%"=="all" set DO_S10=1
if "%STEP%"=="flex" set DO_S10=1
if "%STEP%"=="10"  set DO_S10=1
if defined DO_S10 (
    echo.
    echo [flex 7/9] Flexible LC PG graphs ^(neo4j,falkordb,memgraph,arcadedb,nebula,ladybug%CLOUD_PG%^) + qdrant  [--clean] [graph-backend:langchain] [chunker:langchain] %LANGFLOW_FLAG% %PIPELINE_FLAG%
    %MATRIX% --pg neo4j,falkordb,memgraph,arcadedb,nebula,ladybug%CLOUD_PG% --vector qdrant ^
             --graph-backend langchain ^
             --chunker langchain ^
             --clean %LANGFLOW_FLAG% %PIPELINE_FLAG%
    if !ERRORLEVEL! EQU 0 ( set /a PASS+=1 ) else ( set /a FAIL+=1 )
)

:: ── [flex 8/9] Flexible LC search engines + LC chunker
::   Same 3 search stores as flex 5/9 but with SEARCH_BACKEND=langchain and LC chunker.
::   Tests the LangChain search adapters end-to-end.
if "%STEP%"=="all" set DO_S11=1
if "%STEP%"=="flex" set DO_S11=1
if "%STEP%"=="11"  set DO_S11=1
if defined DO_S11 (
    echo.
    echo [flex 8/9] Flexible LC search engines ^(elasticsearch,opensearch,bm25^) + qdrant  [--clean] [chunker:langchain] [search_backend:langchain] %LANGFLOW_FLAG% %PIPELINE_FLAG%
    %MATRIX% --vector qdrant --search elasticsearch,opensearch,bm25 ^
             --search-backend langchain ^
             --chunker langchain ^
             --clean %LANGFLOW_FLAG% %PIPELINE_FLAG%
    if !ERRORLEVEL! EQU 0 ( set /a PASS+=1 ) else ( set /a FAIL+=1 )
)

:: ── [flex 9/9] Flexible LC vector stores + LC chunker
::   All 10 vector stores tested with VECTOR_BACKEND=langchain and LC chunker.
::   Tests the LangChain vector adapters end-to-end.
::   milvus / weaviate / lancedb / pinecone are LC-only; others also work with LI.
::   neo4j here = vector-only (no graph).  pinecone = cloud from .env.
if "%STEP%"=="all" set DO_S12=1
if "%STEP%"=="flex" set DO_S12=1
if "%STEP%"=="12"  set DO_S12=1
if defined DO_S12 (
    echo.
    echo [flex 9/9] Flexible LC vector stores ^(qdrant,lancedb,postgres,chroma,milvus,weaviate,elasticsearch,opensearch,pinecone,neo4j^)  [--clean] [chunker:langchain] [vector_backend:langchain] %LANGFLOW_FLAG% %PIPELINE_FLAG%
    %MATRIX% --vector qdrant,lancedb,postgres,chroma,milvus,weaviate,elasticsearch,opensearch,pinecone,neo4j ^
             --vector-backend langchain ^
             --chunker langchain ^
             --clean %LANGFLOW_FLAG% %PIPELINE_FLAG%
    if !ERRORLEVEL! EQU 0 ( set /a PASS+=1 ) else ( set /a FAIL+=1 )
)

:: =============================================================================
:: SUMMARY
:: =============================================================================

echo.
echo ============================================================
echo  SUMMARY: %PASS% suite(s) passed,  %FAIL% suite(s) failed
echo ============================================================
if %FAIL% GTR 0 exit /b 1
exit /b 0
