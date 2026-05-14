import json
import threading
from pathlib import Path
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
import uuid
import logging

try:
    import chromadb
    from chromadb.config import Settings
    from sentence_transformers import SentenceTransformer
    VECTOR_AVAILABLE = True
except ImportError:
    VECTOR_AVAILABLE = False

from src.core.config import system_logger, MEMORY_DIR
from src.api.database import clear_strategic_memories, list_strategic_memories, record_strategic_memory
from src.memory.consolidation import consolidate_session_memories, promote_checkpoint
from src.memory.retrieval import search_memory
from src.memory.schema import StrategicMemory, normalize_memory_type, redact_metadata, redact_secrets
from src.auth.rbac import Permission, get_rbac_manager
from src.api.auth_bridge import get_active_user
from src.memory.quant_amp import QuantAmpAtomizer, QIP, QuantumCollapse


def _chroma_safe_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Chroma metadata values must be scalar; preserve nested values as JSON text."""
    safe: Dict[str, Any] = {}
    for key, value in (metadata or {}).items():
        if value is None:
            safe[str(key)] = ""
        elif isinstance(value, (str, int, float, bool)):
            safe[str(key)] = value
        else:
            safe[str(key)] = json.dumps(value, sort_keys=True)
    return safe


class VectorMemoryStore:
    """
    Vector-backed memory store for semantic recall and knowledge persistence.
    Provides session-based storage with cross-session semantic retrieval.
    Enhanced with user context, data isolation, audit logging, and retention policies.
    """

    def __init__(self, session_identifier: str, user_id: Optional[str] = None):
        self.session_id = session_identifier
        self.user_id = user_id or get_active_user()  # Get current user from context
        self._lock = threading.Lock()
        self.rbac_manager = get_rbac_manager()

        if not VECTOR_AVAILABLE:
            system_logger.warning("Vector dependencies not available, falling back to basic memory")
            self._fallback_store = None
            return

        # Initialize ChromaDB client
        self.chroma_client = chromadb.PersistentClient(
            path=str(MEMORY_DIR / "chroma_db"),
            settings=Settings(anonymized_telemetry=False)
        )

        # Get or create collection for this session
        self.collection_name = f"session_{session_identifier}"
        try:
            self.collection = self.chroma_client.get_collection(name=self.collection_name)
        except:
            self.collection = self.chroma_client.create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"}
            )

        # Initialize sentence transformer for embeddings
        self.embedder = SentenceTransformer('all-MiniLM-L6-v2')

        system_logger.info(f"Vector memory store initialized for session: [{self.session_id}], user: [{self.user_id}]")

    def _check_memory_permission(self, permission: Permission) -> bool:
        """Check if current user has memory permission."""
        if not self.user_id:
            # Allow fallback for system operations or unauthenticated access
            return True
        return self.rbac_manager.check_permission(self.user_id, permission)

    def _audit_memory_access(self, action: str, memory_id: str, outcome: str = "success", details: str = ""):
        """Audit memory access for compliance and security tracking."""
        try:
            # This would integrate with the audit log system
            # For now, we log to system logger with user context
            system_logger.info(
                f"MEMORY_AUDIT: user={self.user_id}, action={action}, "
                f"memory_id={memory_id}, outcome={outcome}, details={details}"
            )
        except Exception as e:
            system_logger.error(f"Failed to audit memory access: {e}")

    def _apply_data_isolation_filter(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Apply data isolation filters to ensure users only see their own data."""
        if not self.user_id:
            return metadata  # No filtering for system operations

        # Ensure the memory belongs to the current user
        metadata["user_id"] = self.user_id
        metadata["session_id"] = self.session_id
        return metadata

    def _apply_retention_policy(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Apply data retention policies based on user role."""
        if not self.user_id:
            return metadata

        try:
            user_role = self.rbac_manager._get_user_role(self.user_id)
            if user_role:
                # Define retention periods by role (in days)
                retention_policies = {
                    Permission.ADMIN: 365,      # 1 year
                    Permission.USER: 180,       # 6 months
                    Permission.VIEWER: 90,      # 3 months
                    Permission.AUDITOR: 365,    # 1 year (for compliance)
                }

                # Get the highest retention period applicable to user's roles
                max_retention = 30  # Default minimum
                for permission, days in retention_policies.items():
                    if self.rbac_manager.check_permission(self.user_id, permission):
                        max_retention = max(max_retention, days)

                metadata["retention_days"] = max_retention
                metadata["created_at"] = datetime.utcnow().isoformat()
                metadata["expires_at"] = (datetime.utcnow() + timedelta(days=max_retention)).isoformat()
        except Exception as e:
            system_logger.error(f"Failed to apply retention policy: {e}")
            # Default to 30 days if policy application fails
            metadata["retention_days"] = 30
            metadata["created_at"] = datetime.utcnow().isoformat()
            metadata["expires_at"] = (datetime.utcnow() + timedelta(days=30)).isoformat()

        return metadata

    def add_memory(self, content: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        Add a memory item with semantic embedding.
        Returns memory ID.
        Implements data isolation, audit logging, and retention policies.
        """
        # Check permission
        if not self._check_memory_permission(Permission.MEMORY_WRITE):
            self._audit_memory_access("add_memory_attempt", "unknown", "failure", "Insufficient permissions")
            raise PermissionError("Insufficient permissions to add memory")

        metadata = metadata or {}
        memory_type = normalize_memory_type(str(metadata.get("type") or metadata.get("memory_type") or "execution_insight"))
        clean_content, content_redactions = redact_secrets(content)
        clean_metadata, metadata_redactions = redact_metadata(metadata)
        clean_metadata["memory_type"] = memory_type
        clean_metadata["type"] = memory_type
        if content_redactions or metadata_redactions:
            clean_metadata["redaction_count"] = str(content_redactions + metadata_redactions)

        # Apply data isolation and retention policies
        clean_metadata = self._apply_data_isolation_filter(clean_metadata)
        clean_metadata = self._apply_retention_policy(clean_metadata)

        strategic_memory = StrategicMemory(
            session_id=str(clean_metadata.get("session_id") or self.session_id),
            user_id=str(clean_metadata.get("user_id") or self.user_id),
            memory_type=memory_type,
            content=clean_content,
            importance=float(clean_metadata.get("importance", 0.5) or 0.5),
            source=str(clean_metadata.get("source") or clean_metadata.get("node_source") or "vector_store"),
            confidence=float(clean_metadata.get("confidence", 0.75) or 0.75),
            metadata=clean_metadata,
        ).sanitized()
        memory_id = strategic_memory.id
        record_strategic_memory(strategic_memory.public_dict())

        if not VECTOR_AVAILABLE:
            result = self._add_fallback_memory(clean_content, strategic_memory.metadata, memory_id=memory_id)
            self._audit_memory_access("add_memory", memory_id, "success", f"Stored via fallback: {result}")
            return result

        # Generate embedding
        embedding = self.embedder.encode(clean_content).tolist()

        # [QUANTAMP INTEGRATION]
        # Generate Universal Atom and Logic Pulse
        atom = QuantAmpAtomizer.atomize(clean_content)
        pulse = QIP.synthesize_pulse(atom)
        q_signature = QuantumCollapse.encode(pulse)

        # Prepare metadata
        mem_metadata = {
            "timestamp": datetime.utcnow().isoformat(),
            "session_id": self.session_id,
            "user_id": self.user_id,
            "q_signature": q_signature.hex(), # Store as hex string for Chroma
            **_chroma_safe_metadata(strategic_memory.metadata),
        }

        with self._lock:
            self.collection.add(
                embeddings=[embedding],
                documents=[clean_content],
                metadatas=[mem_metadata],
                ids=[memory_id]
            )

        system_logger.debug(f"Added memory item: [{memory_id}] for user [{self.user_id}]")
        self._audit_memory_access("add_memory", memory_id, "success")
        return memory_id

    def search_memories(
        self,
        query: str,
        limit: int = 5,
        memory_type: str = None,
        scope: str = "matters",
        task_type: str = None,
    ) -> List[Dict[str, Any]]:
        """
        Search tiered memory with policy-aware retrieval.
        Returns list of memory items with content and metadata.
        Implements data isolation - users only see their own data.
        """
        # Check permission
        if not self._check_memory_permission(Permission.MEMORY_READ):
            self._audit_memory_access("search_memories_attempt", "unknown", "failure", "Insufficient permissions")
            raise PermissionError("Insufficient permissions to search memory")

        # Apply user isolation to search - only search user's own memories
        strategic_results = search_memory(
            query,
            session_id=None,  # We handle isolation at the metadata level
            memory_type=memory_type,
            scope=scope,
            task_type=task_type,
            limit=limit * 2  # Get extra to filter by user
        )

        # Filter results to only include user's own memories
        user_memories = []
        for result in strategic_results:
            result_dict = result.public_dict()
            metadata = result_dict.get("metadata", {})
            # Check if memory belongs to current user
            if metadata.get("user_id") == self.user_id or not self.user_id:
                user_memories.append(result_dict)
                if len(user_memories) >= limit:
                    break

        if strategic_results and not VECTOR_AVAILABLE:
            return self._search_fallback_memories(query, limit)

        if not VECTOR_AVAILABLE:
            return self._search_fallback_memories(query, limit)

        # Generate query embedding
        query_embedding = self.embedder.encode(query).tolist()
        
        # [QUANTAMP INTEGRATION]
        # Generate query signature for Resonance check
        query_atom = QuantAmpAtomizer.atomize(query)
        query_pulse = QIP.synthesize_pulse(query_atom)
        query_sig = QuantumCollapse.encode(query_pulse)

        with self._lock:
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=limit * 2,  # Get extra to filter by user
                include=["documents", "metadatas", "distances"]
            )

        memories = []
        if results['ids'] and results['ids'][0]:
            for i, memory_id in enumerate(results['ids'][0]):
                # Check if this memory belongs to the current user
                metadata = results['metadatas'][0][i]
                if metadata.get("user_id") == self.user_id or not self.user_id:
                    # [STRETCH] Calculate Hamming Resonance
                    similarity = 1 - results['distances'][0][i]
                    
                    stored_sig_hex = metadata.get("q_signature")
                    if stored_sig_hex:
                        try:
                            stored_sig = bytes.fromhex(stored_sig_hex)
                            hamming = QuantumCollapse.hamming_distance(query_sig, stored_sig)
                            # Higher resonance means lower Hamming distance
                            # Normalize distance (max bits is 1024, but encoded bits vary by precision)
                            # For BALANCED it's 128 bytes = 1024 bits
                            resonance = 1.0 - (hamming / 1024.0)
                            similarity = (0.7 * similarity) + (0.3 * resonance)
                        except Exception:
                            pass

                    memories.append({
                        "id": memory_id,
                        "content": results['documents'][0][i],
                        "metadata": metadata,
                        "similarity": similarity
                    })
                    if len(memories) >= limit:
                        break

        self._audit_memory_access("search_memories", "multiple", "success", f"Returned {len(memories)} memories")
        return memories

    def get_session_memories(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get all memories for current session.
        Implements data isolation - users only see their own memories.
        """
        # Check permission
        if not self._check_memory_permission(Permission.MEMORY_READ):
            self._audit_memory_access("get_session_memories_attempt", "unknown", "failure", "Insufficient permissions")
            raise PermissionError("Insufficient permissions to get session memories")

        strategic_memories = list_strategic_memories(session_id=self.session_id, include_checkpoints=True, limit=limit * 2)
        if strategic_memories:
            # Filter to only include user's own memories
            user_memories = []
            for memory in strategic_memories:
                # Check if memory belongs to current user
                if memory.get("user_id") == self.user_id or not self.user_id:
                    user_memories.append(memory)
                    if len(user_memories) >= limit:
                        break
            return user_memories

        if not VECTOR_AVAILABLE:
            return self._get_fallback_session_memories(limit)

        with self._lock:
            results = self.collection.get(
                where={"session_id": self.session_id},
                limit=limit * 2,  # Get extra to filter by user
                include=["documents", "metadatas"]
            )

        memories = []
        if results['ids']:
            for i, memory_id in enumerate(results['ids']):
                # Check if this memory belongs to the current user
                metadata = results['metadatas'][i]
                if metadata.get("user_id") == self.user_id or not self.user_id:
                    memories.append({
                        "id": memory_id,
                        "content": results['documents'][i],
                        "metadata": metadata
                    })
                    if len(memories) >= limit:
                        break

        self._audit_memory_access("get_session_memories", "multiple", "success", f"Returned {len(memories)} memories")
        return memories

    def clear_session(self):
        """Clear all memories for this session."""
        # Check permission
        if not self._check_memory_permission(Permission.MEMORY_DELETE):
            self._audit_memory_access("clear_session_attempt", "unknown", "failure", "Insufficient permissions")
            raise PermissionError("Insufficient permissions to clear session")

        clear_strategic_memories(session_id=self.session_id)
        if not VECTOR_AVAILABLE:
            return self._clear_fallback_session()

        with self._lock:
            # Delete collection and recreate
            try:
                self.chroma_client.delete_collection(name=self.collection_name)
            except:
                pass
            self.collection = self.chroma_client.create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"}
            )

        system_logger.info(f"Cleared vector memory for session: [{self.session_id}], user: [{self.user_id}]")
        self._audit_memory_access("clear_session", "session", "success")

    # Fallback methods when vector dependencies unavailable
    def _add_fallback_memory(self, content: str, metadata: Optional[Dict[str, Any]] = None, *, memory_id: str = None) -> str:
        """Fallback to JSONL storage."""
        memory_id = memory_id or str(uuid.uuid4())
        payload = {
            "id": memory_id,
            "timestamp": datetime.utcnow().isoformat(),
            "content": content,
            "metadata": metadata or {}
        }

        fallback_path = MEMORY_DIR / f"fallback_{self.session_id}.jsonl"
        with open(fallback_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload) + "\\n")

        return memory_id

    def _search_fallback_memories(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Fallback search using simple text matching."""
        fallback_path = MEMORY_DIR / f"fallback_{self.session_id}.jsonl"
        if not fallback_path.exists():
            return []

        memories = []
        with open(fallback_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    item = json.loads(line.strip())
                    if query.lower() in item.get("content", "").lower():
                        # Check user isolation for fallback too
                        item_metadata = item.get("metadata", {})
                        if item_metadata.get("user_id") == self.user_id or not self.user_id:
                            memories.append(item)
                            if len(memories) >= limit:
                                break
                except:
                    continue

        return memories

    def _get_fallback_session_memories(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Fallback to get all session memories."""
        fallback_path = MEMORY_DIR / f"fallback_{self.session_id}.jsonl"
        if not fallback_path.exists():
            return []

        memories = []
        with open(fallback_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    memory = json.loads(line.strip())
                    # Check user isolation for fallback too
                    memory_metadata = memory.get("metadata", {})
                    if memory_metadata.get("user_id") == self.user_id or not self.user_id:
                        memories.append(memory)
                        if len(memories) >= limit:
                            break
                except:
                    continue

        return memories

    def _clear_fallback_session(self):
        """Fallback to clear session memories."""
        fallback_path = MEMORY_DIR / f"fallback_{self.session_id}.jsonl"
        if fallback_path.exists():
            fallback_path.unlink()


class MemoryConsolidationAgent:
    """
    Agent responsible for consolidating memories, extracting patterns,
    and creating semantic summaries.
    """

    def __init__(self, vector_store: VectorMemoryStore):
        self.vector_store = vector_store
        system_logger.info("Memory Consolidation Agent initialized")

    def consolidate_session(self) -> Dict[str, Any]:
        """
        Consolidate current session memories into key insights.
        """
        return consolidate_session_memories(self.vector_store.session_id)


# Backward compatibility wrapper
class MemoryCheckpointStore:
    """
    Backward-compatible memory store that delegates to vector store when available.
    Maintains the original interface for existing code.
    Enhanced with user context support.
    """

    def __init__(self, session_identifier: str, user_id: Optional[str] = None):
        self.session_id = session_identifier
        self.user_id = user_id
        self._lock = threading.Lock()

        # Initialize vector store
        self.vector_store = VectorMemoryStore(session_identifier, user_id)
        self.consolidation_agent = MemoryConsolidationAgent(self.vector_store)

        # Keep original file-based checkpoint for compatibility
        from src.core.config import MEMORY_DIR
        self.file_path = MEMORY_DIR / f"session_{self.session_id}.jsonl"

        system_logger.info(f"Enhanced MemoryCheckpointStore instantiated for: [{self.session_id}], user: [{self.user_id}]")

    def add_memory(self, content: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        Add a memory item - delegates to vector store for semantic storage.
        Maintains backward compatibility with original interface.
        """
        return self.vector_store.add_memory(content, metadata)

    def log_graph_checkpoint(self, state_snapshot: Dict[str, Any], triggering_node: str) -> None:
        """
        Enhanced checkpoint logging that stores both in vector memory (for search)
        and maintains original JSONL file (for compatibility).
        """
        # Store in vector memory for semantic search
        checkpoint_content = f"Checkpoint from node [{triggering_node}] at step [{state_snapshot.get('current_step_id', 'unassigned')}]"
        if state_snapshot.get('error_history'):
            checkpoint_content += f" Errors: {[str(e) for e in state_snapshot['error_history']]}"

        self.vector_store.add_memory(
            checkpoint_content,
            {
                "type": "checkpoint",
                "node_source": triggering_node,
                "source": triggering_node,
                "active_step": state_snapshot.get("current_step_id", "unassigned"),
                "session_id": self.session_id,
                "user_id": self.user_id,
                "importance": 0.24,
                "confidence": 1.0,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )
        promote_checkpoint(state_snapshot, triggering_node, self.session_id)

        # Maintain original JSONL file for backward compatibility
        payload = {
            "timestamp": datetime.utcnow().isoformat(),
            "node_source": triggering_node,
            "active_step_flag": state_snapshot.get("current_step_id", "unassigned"),
            "cumulative_errors": [str(e) for e in state_snapshot.get("error_history", [])],
        }

        try:
            with self._lock:
                with open(self.file_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(payload) + "\\n")

            system_logger.debug(f"Enhanced checkpoint stored: [{triggering_node}]")
        except Exception as e:
            system_logger.critical(f"FATAL REPO ERROR: JSON Array corruption detected during checkpoint. Fault: {str(e)}")

    def search_memories(self, query: str, limit: int = 5, memory_type: str = None, scope: str = "matters") -> List[Dict[str, Any]]:
        """Search memories semantically."""
        results = search_memory(query, session_id=None, memory_type=memory_type, scope=scope, limit=limit)
        return [result.public_dict() for result in results]

    def consolidate_session(self) -> Dict[str, Any]:
        """Consolidate session memories."""
        return self.consolidation_agent.consolidate_session()

    def get_session_memories(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get session memories."""
        return list_strategic_memories(session_id=self.session_id, include_checkpoints=True, limit=limit)