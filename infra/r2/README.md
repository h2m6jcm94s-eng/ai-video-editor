# R2 Lifecycle Configuration

Apply the abort-incomplete-multipart rule:

```bash
aws s3api put-bucket-lifecycle-configuration \
  --bucket "$R2_BUCKET_NAME" \
  --endpoint-url "$R2_ENDPOINT" \
  --lifecycle-configuration file://infra/r2/lifecycle.json
```

Verify:

```bash
aws s3api get-bucket-lifecycle-configuration \
  --bucket "$R2_BUCKET_NAME" \
  --endpoint-url "$R2_ENDPOINT"
```
