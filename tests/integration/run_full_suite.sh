#!/usr/bin/env bash
# =============================================================================
# run_full_suite.sh - Full integration test matrix (macOS / Linux / Git Bash)
#
# Same 12 suites as run_full_suite.bat.
#
# Usage (from repo root):
#   ./tests/integration/run_full_suite.sh                        — run all 12 suites
#   ./tests/integration/run_full_suite.sh <step>                 — run one suite by number
#   ./tests/integration/run_full_suite.sh coco                   — run all 3 CocoIndex native suites
#   ./tests/integration/run_full_suite.sh flex                   — run all 9 Flexible suites (default pipeline)
#   ./tests/integration/run_full_suite.sh coco-flex              — flex 4-12 with PIPELINE_BACKEND=cocoindex
#   ./tests/integration/run_full_suite.sh flex --pipeline cocoindex  — same as coco-flex
#   ./tests/integration/run_full_suite.sh langflow               — flex 1-9 with LangFlow UI
#   ./tests/integration/run_full_suite.sh <step> --langflow true — add LangFlow to flex step(s)
#   ./tests/integration/run_full_suite.sh flex --cloud spanner   — add cloud graph stores (off by
#       default) to the PG graph steps (flex 2, 3, 7): spanner, neptune, neptune_analytics
#
# Windows: works under Git Bash or WSL if `uv` is on PATH. Not for cmd.exe.
# =============================================================================

set -uo pipefail

# Repo root = two levels up from this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${REPO_ROOT}"

# Portable lowercase (macOS ships Bash 3.2 — no ${var,,})
_lc() { printf '%s' "$1" | tr '[:upper:]' '[:lower:]'; }

MATRIX=(uv run tests/integration/run_matrix.py)
PASS=0
FAIL=0

STEP="${1:-all}"
STEP_LC="$(_lc "${STEP}")"
LANGFLOW_FLAG=()
PIPELINE_FLAG=()
CLOUD_PG=""   # --cloud spanner[,neptune,...]: appended to the PG graph steps' --pg lists

# Parse optional flags (any position after step)
shift || true
while [[ $# -gt 0 ]]; do
  case "$1" in
    --langflow)
      if [[ "${2:-}" == "true" ]]; then
        LANGFLOW_FLAG=(--langflow true)
        shift
      fi
      ;;
    --cloud)
      if [[ -n "${2:-}" ]]; then
        CLOUD_PG=",${2}"
        shift
      fi
      ;;
    --pipeline)
      if [[ "${2:-}" == "cocoindex" ]]; then
        PIPELINE_FLAG=(--pipeline cocoindex)
        shift
      fi
      ;;
  esac
  shift || true
done

# 'langflow' step alias = flex steps 4-12 with --langflow true
if [[ "${STEP_LC}" == "langflow" ]]; then
  STEP=flex
  STEP_LC=flex
  if [[ ${#LANGFLOW_FLAG[@]} -eq 0 ]]; then
    LANGFLOW_FLAG=(--langflow true)
  fi
fi

# 'coco-flex' step alias = flex steps 4-12 with --pipeline cocoindex
if [[ "${STEP_LC}" == "coco-flex" ]]; then
  STEP=flex
  STEP_LC=flex
  if [[ ${#PIPELINE_FLAG[@]} -eq 0 ]]; then
    PIPELINE_FLAG=(--pipeline cocoindex)
  fi
fi

if [[ ${#LANGFLOW_FLAG[@]} -gt 0 && ${#PIPELINE_FLAG[@]} -gt 0 ]]; then
  echo
  echo "ERROR: --langflow true and --pipeline cocoindex cannot be combined."
  echo "       LangFlow and the CocoIndex pipeline are mutually exclusive."
  exit 1
fi

case "${STEP_LC}" in
  all|coco|flex|1|2|3|4|5|6|7|8|9|10|11|12) ;;
  *)
    echo
    echo "ERROR: Invalid step ${STEP}."
    echo "Usage: run_full_suite.sh [1-12 | coco | flex | coco-flex | langflow | all] [--pipeline cocoindex] [--langflow true] [--cloud spanner,...]"
    echo
    echo "Steps:"
    echo "  1  [coco 1] CocoIndex native data sources"
    echo "  2  [coco 2] CocoIndex native PG graphs"
    echo "  3  [coco 3] CocoIndex native vector stores"
    echo "  4  [flex 1] Flexible data sources (14 sources)"
    echo "  5  [flex 2] Flexible LI PG graphs               [LI chunker]"
    echo "  6  [flex 3] Flexible LC PG graphs               [LI chunker]"
    echo "  7  [flex 4] Flexible vector stores              [LI chunker]"
    echo "  8  [flex 5] Flexible search engines             [LI chunker]"
    echo "  9  [flex 6] Flexible RDF stores                 [LI chunker]"
    echo " 10  [flex 7] Flexible LC PG graphs               [LC chunker, graph_backend=langchain]"
    echo " 11  [flex 8] Flexible LC search engines          [LC chunker, search_backend=langchain]"
    echo " 12  [flex 9] Flexible LC vector stores           [LC chunker, vector_backend=langchain]"
    echo
    echo "  coco-flex — alias for flex --pipeline cocoindex (steps 4-12 under CocoIndex pipeline)"
    echo "  langflow  - alias for flex with --langflow true (steps 4-12)"
    exit 1
    ;;
esac

RUN_COCO=0
RUN_FLEX=0
case "${STEP_LC}" in
  all)  RUN_COCO=1; RUN_FLEX=1 ;;
  coco) RUN_COCO=1 ;;
  flex) RUN_FLEX=1 ;;
  1|2|3) RUN_COCO=1 ;;
  4|5|6|7|8|9|10|11|12) RUN_FLEX=1 ;;
esac

run_suite() {
  local label="$1"
  shift
  echo
  echo "${label}"
  if "${MATRIX[@]}" "$@"; then
    PASS=$((PASS + 1))
  else
    FAIL=$((FAIL + 1))
  fi
}

# =============================================================================
# COCOINDEX PIPELINE TESTS  (steps 1-3)
# =============================================================================

if [[ "${RUN_COCO}" == "1" ]]; then
  echo
  echo "============================================================"
  echo " COCOINDEX PIPELINE TESTS"
  echo "============================================================"
fi

if [[ "${STEP_LC}" == "all" || "${STEP_LC}" == "coco" || "${STEP_LC}" == "1" ]]; then
  run_suite \
    "[coco 1/3] CocoIndex native data sources (filesystem,s3,azure_blob,google_drive) + qdrant + ES  [--clean] [chunker:cocoindex]" \
    --vector qdrant --search elasticsearch \
    --pipeline cocoindex --source-backend cocoindex \
    --graph-backend cocoindex --vector-backend cocoindex \
    --chunker cocoindex \
    --data-source all --clean
fi

if [[ "${STEP_LC}" == "all" || "${STEP_LC}" == "coco" || "${STEP_LC}" == "2" ]]; then
  run_suite \
    "[coco 2/3] CocoIndex native PG graphs (neo4j, falkordb, surrealdb) + qdrant  [--clean] [chunker:cocoindex]" \
    --pg neo4j,falkordb,surrealdb --vector qdrant --search elasticsearch \
    --pipeline cocoindex \
    --graph-backend cocoindex --vector-backend cocoindex \
    --chunker cocoindex \
    --clean
fi

if [[ "${STEP_LC}" == "all" || "${STEP_LC}" == "coco" || "${STEP_LC}" == "3" ]]; then
  run_suite \
    "[coco 3/3] CocoIndex native vector stores (qdrant, lancedb, postgres)  [--clean] [chunker:cocoindex]" \
    --vector qdrant,lancedb,postgres \
    --pipeline cocoindex \
    --graph-backend cocoindex --vector-backend cocoindex \
    --chunker cocoindex \
    --clean
fi

# =============================================================================
# FLEXIBLE GRAPHRAG PIPELINE TESTS  (steps 4-12)
# =============================================================================

if [[ "${RUN_FLEX}" == "1" ]]; then
  echo
  echo "============================================================"
  echo " FLEXIBLE GRAPHRAG PIPELINE TESTS"
  echo "============================================================"
fi

EXTRA_NOTE=""
if [[ ${#LANGFLOW_FLAG[@]} -gt 0 ]]; then
  EXTRA_NOTE=" ${LANGFLOW_FLAG[*]}"
fi
if [[ ${#PIPELINE_FLAG[@]} -gt 0 ]]; then
  EXTRA_NOTE="${EXTRA_NOTE} ${PIPELINE_FLAG[*]}"
fi

if [[ "${STEP_LC}" == "all" || "${STEP_LC}" == "flex" || "${STEP_LC}" == "4" ]]; then
  run_suite \
    "[flex 1/9] Flexible data sources (14 sources) + qdrant + ES  [--clean] [chunker:llamaindex]${EXTRA_NOTE}" \
    --vector qdrant --search elasticsearch \
    --data-source filesystem,web,wikipedia,youtube,alfresco,nuxeo,cmis,s3,box,azure_blob,onedrive,sharepoint,google_drive,gcs \
    --backends llamaindex \
    --chunker llamaindex \
    --clean "${LANGFLOW_FLAG[@]}" "${PIPELINE_FLAG[@]}"
fi

if [[ "${STEP_LC}" == "all" || "${STEP_LC}" == "flex" || "${STEP_LC}" == "5" ]]; then
  run_suite \
    "[flex 2/9] Flexible LI PG graphs (neo4j,falkordb,memgraph,arcadedb,nebula,ladybug${CLOUD_PG}) + qdrant  [--clean] [chunker:llamaindex]${EXTRA_NOTE}" \
    --pg neo4j,falkordb,memgraph,arcadedb,nebula,ladybug${CLOUD_PG} --vector qdrant \
    --graph-backend llamaindex \
    --chunker llamaindex \
    --clean "${LANGFLOW_FLAG[@]}" "${PIPELINE_FLAG[@]}"
fi

if [[ "${STEP_LC}" == "all" || "${STEP_LC}" == "flex" || "${STEP_LC}" == "6" ]]; then
  run_suite \
    "[flex 3/9] Flexible LC PG graphs (neo4j,arangodb,apache_age,hugegraph,surrealdb,tigergraph,arcadedb,falkordb,memgraph,nebula,cosmos_gremlin${CLOUD_PG}) + qdrant  [--clean] [chunker:llamaindex]${EXTRA_NOTE}" \
    --pg neo4j,arangodb,apache_age,hugegraph,surrealdb,tigergraph,arcadedb,falkordb,memgraph,nebula,cosmos_gremlin${CLOUD_PG} \
    --vector qdrant \
    --graph-backend langchain \
    --chunker llamaindex \
    --clean "${LANGFLOW_FLAG[@]}" "${PIPELINE_FLAG[@]}"
fi

if [[ "${STEP_LC}" == "all" || "${STEP_LC}" == "flex" || "${STEP_LC}" == "7" ]]; then
  run_suite \
    "[flex 4/9] Flexible vector stores (qdrant,lancedb,postgres,chroma,milvus,weaviate,elasticsearch,opensearch,pinecone,neo4j)  [--clean] [chunker:llamaindex]${EXTRA_NOTE}" \
    --vector qdrant,lancedb,postgres,chroma,milvus,weaviate,elasticsearch,opensearch,pinecone,neo4j \
    --vector-backend llamaindex \
    --chunker llamaindex \
    --clean "${LANGFLOW_FLAG[@]}" "${PIPELINE_FLAG[@]}"
fi

if [[ "${STEP_LC}" == "all" || "${STEP_LC}" == "flex" || "${STEP_LC}" == "8" ]]; then
  run_suite \
    "[flex 5/9] Flexible LI search engines + qdrant  [--clean] [chunker:llamaindex]${EXTRA_NOTE}" \
    --vector qdrant --search elasticsearch,opensearch,bm25 \
    --search-backend llamaindex \
    --chunker llamaindex \
    --clean "${LANGFLOW_FLAG[@]}" "${PIPELINE_FLAG[@]}"
fi

if [[ "${STEP_LC}" == "all" || "${STEP_LC}" == "flex" || "${STEP_LC}" == "9" ]]; then
  run_suite \
    "[flex 6/9] Flexible RDF stores + qdrant  [--clean] [chunker:llamaindex]${EXTRA_NOTE}" \
    --vector qdrant --rdf fuseki,oxigraph,graphdb \
    --backends llamaindex \
    --chunker llamaindex \
    --clean "${LANGFLOW_FLAG[@]}" "${PIPELINE_FLAG[@]}"
fi

if [[ "${STEP_LC}" == "all" || "${STEP_LC}" == "flex" || "${STEP_LC}" == "10" ]]; then
  run_suite \
    "[flex 7/9] Flexible LC PG graphs (neo4j,falkordb,memgraph,arcadedb,nebula,ladybug${CLOUD_PG}) + qdrant  [--clean] [graph-backend:langchain] [chunker:langchain]${EXTRA_NOTE}" \
    --pg neo4j,falkordb,memgraph,arcadedb,nebula,ladybug${CLOUD_PG} --vector qdrant \
    --graph-backend langchain \
    --chunker langchain \
    --clean "${LANGFLOW_FLAG[@]}" "${PIPELINE_FLAG[@]}"
fi

if [[ "${STEP_LC}" == "all" || "${STEP_LC}" == "flex" || "${STEP_LC}" == "11" ]]; then
  run_suite \
    "[flex 8/9] Flexible LC search engines (elasticsearch,opensearch,bm25) + qdrant  [--clean] [chunker:langchain] [search_backend:langchain]${EXTRA_NOTE}" \
    --vector qdrant --search elasticsearch,opensearch,bm25 \
    --search-backend langchain \
    --chunker langchain \
    --clean "${LANGFLOW_FLAG[@]}" "${PIPELINE_FLAG[@]}"
fi

if [[ "${STEP_LC}" == "all" || "${STEP_LC}" == "flex" || "${STEP_LC}" == "12" ]]; then
  run_suite \
    "[flex 9/9] Flexible LC vector stores (qdrant,lancedb,postgres,chroma,milvus,weaviate,elasticsearch,opensearch,pinecone,neo4j)  [--clean] [chunker:langchain] [vector_backend:langchain]${EXTRA_NOTE}" \
    --vector qdrant,lancedb,postgres,chroma,milvus,weaviate,elasticsearch,opensearch,pinecone,neo4j \
    --vector-backend langchain \
    --chunker langchain \
    --clean "${LANGFLOW_FLAG[@]}" "${PIPELINE_FLAG[@]}"
fi

# =============================================================================
# SUMMARY
# =============================================================================

echo
echo "============================================================"
echo " SUMMARY: ${PASS} suite(s) passed,  ${FAIL} suite(s) failed"
echo "============================================================"
if [[ "${FAIL}" -gt 0 ]]; then
  exit 1
fi
exit 0
