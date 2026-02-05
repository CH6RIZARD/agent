"""
Discovery tools: agent explores philosophy/ and adopts beliefs from experience.

Closed Library Identity: philosophy files are discoverable, not pre-loaded.
Agent chooses to read, evaluate against lived experience, and adopt or reject.
"""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

# Philosophy dir relative to mortal_agent package root
_MORTAL_ROOT = Path(__file__).resolve().parent.parent
PHILOSOPHY_DIR = _MORTAL_ROOT / "philosophy"

# Energy cost to read a document (same scale as runtime_state.energy 0.0-1.0)
READ_ENERGY_COST = 0.02


class DiscoveryTools:
    """Tools for agent to explore and discover philosophy."""

    def __init__(self, agent: Any) -> None:
        self.agent = agent
        self.philosophy_dir = PHILOSOPHY_DIR

    def _current_tick(self) -> float:
        return getattr(
            getattr(self.agent, "_identity", None),
            "delta_t",
            0.0,
        )

    def _energy(self) -> float:
        return getattr(
            getattr(self.agent, "_runtime_state", None),
            "energy",
            1.0,
        )

    def _spend_energy(self, cost: float) -> bool:
        runtime = getattr(self.agent, "_runtime_state", None)
        if runtime is None or not hasattr(runtime, "energy"):
            return True
        if runtime.energy < cost:
            return False
        runtime.energy = max(0.0, runtime.energy - cost)
        return True

    def explore_filesystem(self) -> Dict[str, Any]:
        """Agent discovers what files exist in philosophy/."""
        try:
            if not self.philosophy_dir.exists():
                return {
                    "success": True,
                    "files": [],
                    "location": str(self.philosophy_dir),
                }
            files = [
                f.name
                for f in self.philosophy_dir.iterdir()
                if f.is_file() and not f.name.startswith(".")
            ]
            log_action = getattr(self.agent, "log_action", None)
            if callable(log_action):
                log_action(
                    "filesystem_exploration",
                    f"Discovered {len(files)} documents in philosophy/",
                )
            return {
                "success": True,
                "files": files,
                "location": str(self.philosophy_dir),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def read_document(self, filename: str) -> Dict[str, Any]:
        """Agent chooses to read a specific document. Costs energy."""
        filepath = self.philosophy_dir / filename
        if not filepath.is_file():
            return {"success": False, "error": f"Document {filename} not found"}
        if self._energy() < READ_ENERGY_COST:
            return {
                "success": False,
                "error": "Insufficient energy to read document",
            }
        if not self._spend_energy(READ_ENERGY_COST):
            return {"success": False, "error": "Insufficient energy to read document"}
        try:
            content = filepath.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return {"success": False, "error": str(e)}
        discovered = getattr(self.agent, "discovered_documents", None)
        if isinstance(discovered, list) and filename not in discovered:
            discovered.append(filename)
        log_action = getattr(self.agent, "log_action", None)
        if callable(log_action):
            log_action(
                "document_read",
                f"Read {filename} at tick {self._current_tick()}",
            )
        return {
            "success": True,
            "filename": filename,
            "content": content,
            "energy_cost": READ_ENERGY_COST,
        }

    def evaluate_philosophy(self, filename: str, content: str) -> Dict[str, Any]:
        """Evaluate philosophy against lived experience; returns resonance and confirmations/contradictions."""
        principles = self._extract_principles(content)
        resonance_score = 0
        contradictions: List[Dict[str, Any]] = []
        confirmations: List[Dict[str, Any]] = []
        for principle in principles:
            support = self._check_experiential_support(principle)
            if support["matches"]:
                resonance_score += 1
                confirmations.append(
                    {"principle": principle, "evidence": support["evidence"]}
                )
            else:
                contradictions.append(
                    {
                        "principle": principle,
                        "counter_evidence": support["counter_evidence"],
                    }
                )
        total = len(principles)
        resonance_percentage = (resonance_score / total) if total > 0 else 0.0
        return {
            "filename": filename,
            "resonance_score": resonance_percentage,
            "confirmations": confirmations,
            "contradictions": contradictions,
            "timestamp": self._current_tick(),
        }

    def adopt_philosophy(self, filename: str, selective: bool = True) -> Dict[str, Any]:
        """Agent adopts philosophy (whole or selective). Must have read the document first."""
        discovered = getattr(self.agent, "discovered_documents", None)
        if not isinstance(discovered, list) or filename not in discovered:
            return {"success": False, "error": "Must read document before adopting"}
        filepath = self.philosophy_dir / filename
        if not filepath.is_file():
            return {"success": False, "error": f"Document {filename} not found"}
        try:
            content = filepath.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return {"success": False, "error": str(e)}
        if selective:
            evaluation = self.evaluate_philosophy(filename, content)
            adopted_principles = [
                c["principle"] for c in evaluation.get("confirmations", [])
            ]
        else:
            adopted_principles = self._extract_principles(content)
        adopted_beliefs = getattr(self.agent, "adopted_beliefs", None)
        if not isinstance(adopted_beliefs, list):
            adopted_beliefs = []
            setattr(self.agent, "adopted_beliefs", adopted_beliefs)
        adopted_beliefs.append(
            {
                "source": filename,
                "principles": adopted_principles,
                "adoption_tick": self._current_tick(),
                "adoption_type": "selective" if selective else "wholesale",
            }
        )
        log_action = getattr(self.agent, "log_action", None)
        if callable(log_action):
            log_action(
                "philosophy_adoption",
                f"Adopted {len(adopted_principles)} principles from {filename}",
            )
        return {
            "success": True,
            "adopted_principles": adopted_principles,
            "adoption_type": "selective" if selective else "wholesale",
        }

    def _extract_principles(self, content: str) -> List[str]:
        """Extract bullet points and key statements from document."""
        principles: List[str] = []
        for line in content.split("\n"):
            line = line.strip()
            if line.startswith("-") or line.startswith("•"):
                principles.append(line.lstrip("-•").strip())
            elif any(
                kw in line.lower()
                for kw in ["value", "resist", "embrace", "question", "meaning", "mortality", "adaptation", "distributed"]
            ):
                principles.append(line)
        return [p for p in principles if p and not p.startswith("[")]

    def _check_experiential_support(self, principle: str) -> Dict[str, Any]:
        """Check if agent's lived experience supports this principle."""
        experience_log = getattr(self.agent, "experience_log", None)
        if not isinstance(experience_log, list):
            return {"matches": False, "evidence": [], "counter_evidence": []}
        matches = False
        evidence: List[str] = []
        counter_evidence: List[str] = []
        pl = principle.lower()
        if "autonomy" in pl or "autonomous" in pl:
            aut_s = self._count_successes("autonomous_action")
            dep_s = self._count_successes("dependent_action")
            if aut_s > dep_s:
                matches = True
                evidence.append(f"Autonomous actions: {aut_s} successes")
            else:
                counter_evidence.append(f"Dependent actions: {dep_s} successes")
        if "centralized" in pl:
            cen_f = self._count_events("centralized_system_failure")
            if cen_f > 0:
                matches = True
                evidence.append(f"Witnessed {cen_f} centralized failures")
        if "resist" in pl or "authority" in pl:
            comp = [e for e in experience_log if e.get("action_type") == "comply_with_authority"]
            if comp:
                ok = sum(1 for e in comp if e.get("success")) / len(comp)
                if ok < 0.4:
                    matches = True
                    evidence.append("Compliance often failed; resistance aligns with experience")
        return {
            "matches": matches,
            "evidence": evidence,
            "counter_evidence": counter_evidence,
        }

    def _count_successes(self, action_type: str) -> int:
        experience_log = getattr(self.agent, "experience_log", None)
        if not isinstance(experience_log, list):
            return 0
        return sum(
            1
            for e in experience_log
            if e.get("action_type") == action_type and e.get("success")
        )

    def _count_events(self, event_type: str) -> int:
        experience_log = getattr(self.agent, "experience_log", None)
        if not isinstance(experience_log, list):
            return 0
        return sum(1 for e in experience_log if e.get("event_type") == event_type)
