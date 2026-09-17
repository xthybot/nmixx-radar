# Deployment overview

Copy `.sample.env` to `.env`, replace the bootstrap password and public URL, then run `bash install.sh`. The systemd templates in `deploy/systemd/` run the site and periodic update jobs. The Nginx template in `deploy/nginx/` terminates HTTPS on port 443 and proxies to `127.0.0.1:32765`.

`APP_HOST=0.0.0.0` retains direct local-network access on port 32765. Direct HTTP login is limited to private peers and is less secure than HTTPS; administration and Push management require the public HTTPS URL.

Back up the configured `DATA_DIR` while the application service is stopped, or use the provided backup script after it is installed. Do not copy runtime data into Git.
