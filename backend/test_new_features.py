import asyncio
import httpx

BASE_URL = "http://127.0.0.1:8000"

async def test_features():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=15.0) as client:
        print("=== 1. Testing Chat Suggestions ===")
        suggestions = [
            "فحص سرعة الشبكة",
            "الاستعلام عن الرصيد والصلاحية",
            "طريقة شحن كروت الهوت سبوت",
            "طلب تجديد اشتراك شهري",
            "حل مشكلة تقطيع أو بطء الاتصال",
            "ما هي الباقات المتوفرة؟",
        ]
        test_user = "client_test_user"
        for s in suggestions:
            res = await client.post("/client/chat", json={"username": test_user, "message": s})
            assert res.status_code == 200, f"Failed post chat: {res.text}"
        
        chat_res = await client.get("/client/chat", params={"username": test_user})
        assert chat_res.status_code == 200
        msgs = chat_res.json()
        print(f"Total chat messages for {test_user}: {len(msgs)}")
        bot_msgs = [m for m in msgs if m["sender"] == "bot"]
        print(f"Bot responses generated: {len(bot_msgs)}")
        assert len(bot_msgs) >= len(suggestions), "Missing bot responses"
        print("Sample bot response:", bot_msgs[0]["message"][:80], "...")
        print(" Chat suggestions test PASSED!\n")

        print("=== 2. Testing Admin Login ===")
        login_res = await client.post(
            "/auth/login",
            data={"username": "admin", "password": "adminadmin"},
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        assert login_res.status_code == 200, f"Login failed: {login_res.text}"
        token = login_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        print("Admin login successful. Token acquired.\n")

        print("=== 3. Testing Owner Custom Cards Entry & Printing ===")
        custom_payload = {
            "profile": "1 Day",
            "hide_password": False,
            "cards": [
                {"username": "VIP_9001", "password": "pass_9001"},
                {"username": "VIP_9002", "password": "pass_9002"},
                {"username": "VIP_9003"}  # password omitted, should match username
            ]
        }
        custom_res = await client.post("/cards/custom", json=custom_payload, headers=headers)
        assert custom_res.status_code == 200, f"Custom cards failed: {custom_res.text}"
        batch_data = custom_res.json()
        batch_id = batch_data["id"]
        print(f"Custom batch #{batch_id} created successfully with count {batch_data['count']}!")

        # Test PDF download
        pdf_res = await client.get(f"/cards/{batch_id}/pdf", headers=headers)
        assert pdf_res.status_code == 200, f"PDF fetch failed: {pdf_res.status_code}"
        assert pdf_res.headers.get("content-type") == "application/pdf"
        assert len(pdf_res.content) > 500
        print(f"PDF downloaded successfully! Size: {len(pdf_res.content)} bytes.")
        print(" Custom cards & PDF generation test PASSED!\n")

        print("=== 4. Testing Emergency Router Reboot Button ===")
        reboot_res = await client.post("/mikrotik/reboot", headers=headers)
        assert reboot_res.status_code == 200, f"Reboot failed: {reboot_res.text}"
        reboot_data = reboot_res.json()
        print("Reboot response:", reboot_data)
        assert reboot_data["status"] == "success"
        print(" Router reboot test PASSED!\n")

        print("ALL TESTS PASSED SUCCESSFULLY! ")

if __name__ == "__main__":
    asyncio.run(test_features())
