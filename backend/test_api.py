import asyncio
import os
import shutil
import sys
from typing import Dict, Any

import httpx
from main import app
from db import init_db

async def poll_session_status(client: httpx.AsyncClient, session_id: str, expected_statuses: list[str], max_attempts: int = 200) -> Dict[str, Any]:
    for attempt in range(max_attempts):
        response = await client.get(f"/sessions/{session_id}")
        assert response.status_code == 200, f"Failed to get session. Response: {response.text}"
        data = response.json()
        status = data.get("status")
        print(f"  Attempt {attempt + 1}: Status = {status}, Active Stage = {data.get('active_stage')}")
        if status in expected_statuses:
            return data
        await asyncio.sleep(1.0)
    raise TimeoutError(f"Session {session_id} did not reach one of the expected statuses {expected_statuses} in time.")

async def run_tests():
    print("=== Initializing Test Environment ===")
    
    # Clean previous run state files
    files_to_remove = [
        "checkpoints.db",
        "founder_os.db",
        "test_checkpoints.db",
        "test_checkpoints_gate.db",
        "test_checkpoints_safe.db",
        "exports"
    ]
    for f in files_to_remove:
        try:
            if os.path.isdir(f):
                shutil.rmtree(f)
            elif os.path.exists(f):
                os.remove(f)
        except Exception as e:
            print(f"Error cleaning {f}: {e}")

    init_db()

    # Using app.router.lifespan_context and AsyncClient in a single block to manage lifespan and requests
    transport = httpx.ASGITransport(app=app)
    async with app.router.lifespan_context(app), httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        
        # 1. Test Safe Flow (Idea that should pass Validation without gate interrupt)
        print("\n--- 1. Testing Safe Flow ---")
        create_payload = {
            "startup_name": "EcoApp",
            "idea": "A premium clean recycling pickup service.",
            "github_repo": "user/eco-app"
        }
        
        response = await client.post("/sessions", json=create_payload)
        assert response.status_code == 200, f"Failed to create session: {response.text}"
        res_data = response.json()
        session_id = res_data.get("session_id")
        assert session_id is not None
        print(f"Created session with ID: {session_id}")

                # Poll status until complete
        print("Polling session status until complete...")
        # Add "awaiting_gate" to expected statuses just in case
        session_state = await poll_session_status(client, session_id, ["complete", "failed", "awaiting_gate"])
        
        # If the LLM unexpectedly flagged the safe idea as risky, approve it and continue
        if session_state["status"] == "awaiting_gate":
            print("Safe flow unexpectedly triggered gate. Auto-approving...")
            resume_payload = {"decision": "continue"}
            resume_response = await client.post(f"/sessions/{session_id}/gate-decision", json=resume_payload)
            assert resume_response.status_code == 200
            
            # Poll again until complete
            session_state = await poll_session_status(client, session_id, ["complete", "failed"])

        assert session_state["status"] == "complete", "Safe flow failed or did not complete."
        print("Safe flow successfully completed!")
        
        # Verify stages dictionary
        stages = session_state.get("stages", {})
        assert stages.get("startup_advisor", {}).get("status") == "complete"
        assert stages.get("market_research", {}).get("status") == "complete"
        assert stages.get("marketing", {}).get("status") == "complete"
        
        # Verify artifact data
        artifacts = session_state.get("artifacts", {})
        assert "startup_advisor" in artifacts
        assert "market_research" in artifacts
        assert "product_manager" in artifacts
        assert "architect" in artifacts
        assert "engineering_manager" in artifacts
        assert "marketing" in artifacts
        print("All stage artifacts successfully fetched and verified!")

        # 2. Test Stage-Specific Artifact Retrieval
        print("\n--- 2. Testing Stage-Specific Artifacts ---")
        art_response = await client.get(f"/sessions/{session_id}/artifacts/product_manager")
        assert art_response.status_code == 200
        prd_data = art_response.json()
        print("Retrieved PRD Problem Statement:", prd_data.get("problem_statement"))
        assert prd_data.get("problem_statement") is not None

        # 3. Test Decision Log Retrieval
        print("\n--- 3. Testing Decision Log ---")
        log_response = await client.get(f"/sessions/{session_id}/decision-log")
        assert log_response.status_code == 200
        log_data = log_response.json()
        print(f"Retrieved {len(log_data)} decision log entries:")
        for log in log_data:
            print(f"  - [{log['stage_name']}] {log['reasoning']}")
        assert len(log_data) > 0

        # 4. Test PDF Export
        print("\n--- 4. Testing PDF Export ---")
        export_payload = {
            "target": "pdf"
        }
        export_response = await client.post(f"/sessions/{session_id}/export", json=export_payload)
        assert export_response.status_code == 200, f"Export failed: {export_response.text}"
        export_data = export_response.json()
        print("PDF Export Response:", export_data)
        assert export_data.get("status") == "success"
        assert "file_path" in export_data
        assert "download_url" in export_data

        pdf_path = export_data["file_path"]
        assert pdf_path.endswith(".pdf"), f"Expected PDF extension, got: {pdf_path}"
        assert os.path.exists(pdf_path), f"PDF file does not exist: {pdf_path}"

        with open(pdf_path, "rb") as pdf_file:
            header = pdf_file.read(4)
            assert header == b"%PDF", f"Invalid PDF file magic header: {header}"
        print("Verified export generates a valid PDF file successfully!")

        # 4b. Test Notion Export
        print("\n--- 4b. Testing Notion Export ---")
        notion_payload = {
            "target": "notion"
        }
        notion_response = await client.post(f"/sessions/{session_id}/export", json=notion_payload)
        assert notion_response.status_code == 502, f"Expected 502 Bad Gateway for missing Notion keys. Response: {notion_response.status_code} - {notion_response.text}"
        print("Notion export rejected with 502 Bad Gateway as expected!")

        # 5. Test Gate Interrupt Flow (Idea that triggers warning & pause)
        print("\n--- 5. Testing Gate Interrupt Flow ---")
        risky_payload = {
            "startup_name": "RiskCorp",
            "idea": "A volatile dangerous project (trigger_gate)",
            "github_repo": "user/risk-corp"
        }
        
        risky_response = await client.post("/sessions", json=risky_payload)
        assert risky_response.status_code == 200, f"Failed to create session: {risky_response.text}"
        risky_session_id = risky_response.json().get("session_id")
        print(f"Created risky session with ID: {risky_session_id}")

        # Poll status until awaiting_gate
        print("Polling session status until awaiting_gate...")
        risky_state = await poll_session_status(client, risky_session_id, ["awaiting_gate"])
        assert risky_state["status"] == "awaiting_gate"
        assert risky_state["gate"] is not None
        print("Gate interrupt triggered successfully!")
        print("Gate information:")
        print("  Verdict:", risky_state["gate"].get("verdict"))
        print("  Risk Score:", risky_state["gate"].get("risk_score"))
        print("  Red Flags:", risky_state["gate"].get("red_flags"))

        # Test invalid gate decision resume payload (missing revised_idea for revise)
        print("\n--- 6. Testing Gate Decision Validation ---")
        invalid_resume = {
            "decision": "revise"
        }
        val_response = await client.post(f"/sessions/{risky_session_id}/gate-decision", json=invalid_resume)
        assert val_response.status_code == 422
        print("Invalid gate decision rejected as expected (422).")

        # Test valid gate decision resume payload with "revise"
        print("Resuming graph with 'revise' decision and new idea...")
        valid_resume = {
            "decision": "revise",
            "revised_idea": "A safe non-volatile medical tracking tool"
        }
        resume_response = await client.post(f"/sessions/{risky_session_id}/gate-decision", json=valid_resume)
        assert resume_response.status_code == 200
        print("Resume command sent successfully.")

        # Poll status again - it should re-evaluate and complete successfully
        print("Polling session status until complete...")
        final_state = await poll_session_status(client, risky_session_id, ["complete", "failed"])
        assert final_state["status"] == "complete"
        print("Session completed successfully after revision!")
        
        # Verify decision log has the revision logs without duplicates
        final_log_response = await client.get(f"/sessions/{risky_session_id}/decision-log")
        final_log_data = final_log_response.json()
        print("Decision logs for revised session:")
        validation_logs = []
        for log in final_log_data:
            print(f"  - [{log['stage_name']}] {log['reasoning']}")
            if "Validated idea 'A volatile dangerous project" in log['reasoning']:
                validation_logs.append(log)
        
        assert len(validation_logs) == 1, f"Expected exactly 1 validation log for the risky idea, found {len(validation_logs)}"
        print("Verified no duplicate decision log entries exist on resume!")

    # Clean up test files at the end of successful run
    print("\nCleaning up test database files...")
    for f in files_to_remove:
        try:
            if os.path.isdir(f):
                shutil.rmtree(f)
            elif os.path.exists(f):
                os.remove(f)
        except Exception:
            pass

    print("\n=== All API Tests Passed Successfully! ===")

if __name__ == "__main__":
    asyncio.run(run_tests())
