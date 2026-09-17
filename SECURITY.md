# 安全政策

請勿在公開 GitHub Issue 回報安全問題。請私下聯絡 repository 擁有者，並提供受影響版本、重現步驟、影響範圍與安全的概念驗證。請勿附上密碼、session cookie、Push 訂閱 endpoint、VAPID 金鑰或使用者資料。

部署時必須妥善保護 `.env` 與 `data/`，公開存取一律使用 HTTPS，並將應用程式原始埠限制於可信任的本機或區域網路。
