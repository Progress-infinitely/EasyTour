# 褰撳墠椤圭洰鐨勭ず渚嬬幆澧冨彉閲忥紙灏忕櫧鐗堬級
#
# 杩欎笉鏄粰鐢熶骇鐜鐩存帴鐢ㄧ殑瀵嗛挜鏂囦欢锛?# 鑰屾槸缁欎綘鐪嬧€滆繖涓」鐩埌搴曢渶瑕侀厤鍝簺涓滆タ鈥濄€?#
# 鏈€閫傚悎鐨勯槄璇婚『搴忥細
# 1. 鍏堢湅杩欎釜鏂囦欢锛岀煡閬撴湁鍝簺閰嶇疆椤?# 2. 鍐嶇湅 `.env`锛岀悊瑙ｄ綘鏈満瀹為檯鍦ㄧ敤浠€涔堝€?# 3. 鍐嶇湅 `easytour/processor/*/config.py`锛岀悊瑙ｈ繖浜涢厤缃細鍙樻垚鍝簺 Python 瀛楁
# 4. 鏈€鍚庡幓鐪嬪叿浣撹妭鐐癸紝鐞嗚В杩欎簺瀛楁鎺у埗浜嗗摢涓€姝ラ€昏緫
#
# 浣犲彲浠ュ厛璁颁綇涓€涓渶绠€鍗曠殑瑙勫緥锛?# - *_KEY / *_SECRET锛氬嚟璇侊紝鍛婅瘔杩滅▼鏈嶅姟鈥滀綘鏄皝鈥?# - *_BASE / *_URL / *_ENDPOINT锛氬湴鍧€锛屽憡璇夌▼搴忊€滆姹傝鍙戝埌鍝噷鈥?# - *_MODEL锛氬憡璇夌▼搴忊€滆鐢ㄥ摢涓ā鍨嬧€?# - *_COLLECTION / *_NAME锛氬憡璇夌▼搴忊€滄暟鎹鏀惧湪鍝釜鍚嶅瓧涓嬮潰鈥?
# ==========================================================
# 1. 杩滅▼妯″瀷鍩虹閰嶇疆
# ==========================================================
# OPENAI_API_KEY锛氳繙绋嬫ā鍨嬫湇鍔＄殑璁块棶瀵嗛挜銆?# 杩欎釜椤圭洰閲岀殑 LLM銆乪mbedding銆乺erank 绛夎繙绋嬭兘鍔涳紝閫氬父閮介渶瑕佸畠銆?OPENAI_API_KEY=

# OPENAI_API_BASE锛氳繙绋嬫ā鍨嬫湇鍔″湴鍧€銆?# 鏂囨湰妯″瀷璋冪敤閫氬父浼氳蛋杩欓噷銆?OPENAI_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1

# LLM_DEFAULT_MODEL锛氶粯璁ゆ枃鏈ā鍨嬪悕銆?# 涓讳綋璇嗗埆銆丠yDE 鐢熸垚銆佹渶缁堢瓟妗堢敓鎴愶紝閫氬父閮戒細鐢ㄥ埌瀹冦€?LLM_DEFAULT_MODEL=qwen-flash

# VL_MODEL锛氳瑙夋ā鍨嬪悕銆?# 涓昏缁?Markdown 鍥剧墖澶勭悊鑺傜偣鐢ㄦ潵鐢熸垚鍥剧墖鎽樿銆?VL_MODEL=qwen3-vl-flash


# ==========================================================
# 2. PDF 瑙ｆ瀽閰嶇疆锛圡inerU锛?# ==========================================================
# MINERU_API_KEY锛歁inerU 鐨勮闂瘑閽ャ€?# 濡傛灉浣犺瀵煎叆 PDF锛岃繖涓緢閲嶈锛屽洜涓?PDF 闇€瑕佸厛杞垚 Markdown銆?MINERU_API_KEY=

# MINERU_API_BASE锛歁inerU 鎺ュ彛鍦板潃銆?MINERU_API_BASE=https://mineru.net/api/v4

# MINERU_MODEL_VERSION锛歁inerU 瑙ｆ瀽妯″紡鎴栫増鏈€?# 涓€鑸繚鎸佸綋鍓嶅€煎嵆鍙€?MINERU_MODEL_VERSION=vlm


# ==========================================================
# 3. 鏈湴涓棿浠讹細Milvus / MinIO / Mongo
# ==========================================================
# MILVUS_URL锛歁ilvus 鍚戦噺鏁版嵁搴撳湴鍧€銆?# 瀵煎叆閾句細鎶?chunk 鍚戦噺鍐欒繘鍘伙紝鏌ヨ閾句細浠庤繖閲屽仛鐩镐技搴︽绱€?MILVUS_URL=http://127.0.0.1:19530

# MINIO_ENDPOINT锛歁inIO 鍦板潃銆?# 鍘熷鏂囦欢銆佸浘鐗囩瓑瀵硅薄浼氬瓨杩欓噷銆?MINIO_ENDPOINT=127.0.0.1:9000

# MINIO_ACCESS_KEY锛歁inIO 鐧诲綍璐﹀彿銆?MINIO_ACCESS_KEY=minioadmin

# MINIO_SECRET_KEY锛歁inIO 鐧诲綍瀵嗙爜銆?MINIO_SECRET_KEY=minioadmin

# MINIO_BUCKET_NAME锛歁inIO 妗跺悕銆?# 鍥剧墖鍜屾枃浠舵渶缁堜細鏀惧埌杩欎釜妗堕噷銆?MINIO_BUCKET_NAME=knowledge-base-v2

# MINIO_SECURE锛氭槸鍚﹂€氳繃 HTTPS 璁块棶 MinIO銆?# false = HTTP锛宼rue = HTTPS銆?MINIO_SECURE=false

# MONGO_URL锛歁ongo 鏁版嵁搴撳湴鍧€銆?# 鑱婂ぉ鍘嗗彶榛樿浼氫紭鍏堝瓨鍒?Mongo銆?MONGO_URL=mongodb://admin:123456@127.0.0.1:27017

# MONGO_DB_NAME锛歁ongo 鏁版嵁搴撳悕銆?MONGO_DB_NAME=kb001


# ==========================================================
# 4. 鍚戦噺鍖栫浉鍏抽厤缃?# ==========================================================
# EMBEDDING_DIM锛氬悜閲忕淮搴︺€?# 蹇呴』鍜岃繙绋?embedding 妯″瀷杈撳嚭缁村害涓€鑷达紝涔熻鍜?Milvus 闆嗗悎缁撴瀯涓€鑷淬€?EMBEDDING_DIM=1024

# EMBEDDING_MODEL锛歟mbedding 妯″瀷鍚嶃€?# 瀹冭礋璐ｆ妸鏂囨湰杞垚鍚戦噺銆?EMBEDDING_MODEL=text-embedding-v4

# EMBEDDING_PROVIDER锛歟mbedding 鎻愪緵鏂广€?# 褰撳墠椤圭洰涓€鑸繚鎸?dashscope 鍗冲彲銆?EMBEDDING_PROVIDER=dashscope


# ==========================================================
# 5. 鑱旂綉鎼滅储澧炲己锛堝彲閫夛級
# ==========================================================
# ENABLE_WEB_SEARCH锛氭槸鍚﹀惎鐢ㄨ仈缃戞悳绱㈠寮恒€?# true 琛ㄧず鏌ヨ閾句細棰濆璋冪敤 WebSearch MCP锛堥€氳繃 Streamable HTTP 浼犺緭锛夈€?ENABLE_WEB_SEARCH=true

# MCP_DASHSCOPE_BASE_URL锛氳仈缃戞悳绱?MCP 鏈嶅姟鍦板潃銆?# 褰撳墠搴斾娇鐢?/mcp 缁撳熬鐨?Streamable HTTP 鍦板潃銆?# 濡傛灉浠嶅啓鏃х増 /sse 鍦板潃锛屼唬鐮侀噷浼氳嚜鍔ㄥ吋瀹硅浆鎹㈡垚 /mcp銆?MCP_DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/api/v1/mcps/WebSearch/mcp


# ==========================================================
# 6. FastAPI 鏈嶅姟鍚姩閰嶇疆
# ==========================================================
# KNOWLEDGE_API_HOST锛氭湇鍔＄洃鍚湴鍧€銆?KNOWLEDGE_API_HOST=0.0.0.0

# KNOWLEDGE_API_PORT锛氭湇鍔＄洃鍚鍙ｃ€?KNOWLEDGE_API_PORT=8000

