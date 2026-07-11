# نشر تلقائي على يوتيوب - دليل التشغيل

## تصحيح مهم على الخطوات السابقة

سبق وقلت إنك بتحتاج تحط الـ `client_secret_*.json` نفسه بـ GitHub Secrets باسم `YOUTUBE_CREDENTIALS`.
**هذا غير دقيق.** الصح:

- `client_secret_*.json` يبقى على جهازك فقط (محلي، ما بينرفع لـ GitHub أبداً).
- بتستخدمه مرة وحدة بس لتوليد `token.json` (فيه refresh token).
- `token.json` هو الملف الوحيد الي بيروح لـ GitHub Secrets، باسم **`YOUTUBETOKENJSON`** (بدون underscores، لتفادي مشاكل كتابة الـ underscore).
- هذا الـ token بيتجدد نفسه تلقائياً (auto-refresh) بدون ما تحتاج تعمل consent screen مرة ثانية.

## ملفات المشروع

```
requirements.txt
scripts/generate_token.py     -> شغّله محلياً مرة وحدة فقط
scripts/youtube_upload.py     -> رفع فيديو واحد (يستخدمه publish_all.py)
scripts/publish_all.py        -> يفحص videos/to_upload/ ويرفع كل شي جديد
.github/workflows/youtube_publish.yml  -> الأتمتة على GitHub Actions
videos/to_upload/              -> حط هون الفيديو + JSON ميتاداتا (+ صورة مصغرة اختياري)
videos/uploaded/                -> أرشيف الميتاداتا بعد الرفع
uploaded_manifest.json          -> سجل يمنع رفع نفس الفيديو مرتين
```

## خطوات التشغيل (بعد ما تخلص الخطوات 1-9 من قبل)

### 1. ثبّت المتطلبات محلياً
```bash
pip install -r requirements.txt
```

### 2. ولّد الـ token مرة وحدة (على جهازك، مش على GitHub)
```bash
python scripts/generate_token.py --client-secret /path/to/client_secret_XXXX.json
```
رح يفتح متصفح، سجّل دخول ووافق. رح ينطلع ملف `token.json` بنفس المجلد.

⚠️ لو الـ app لسا بوضع "Testing" بـ OAuth consent screen (وهذا الافتراضي)، لازم تضيف حسابك Google كـ **Test User** من:
Google Cloud Console → APIs & Services → OAuth consent screen → Test users → Add users

### 3. انسخ محتوى token.json لـ GitHub Secret
- افتح `token.json` بـ notepad، انسخ كل المحتوى
- Repo على GitHub → Settings → Secrets and variables → Actions → New repository secret
- Name: `YOUTUBETOKENJSON`
- Secret: (الصق المحتوى)
- Add secret
- احذف `token.json` من جهازك بعدها (أو خزّنه بمكان آمن، بس متنشره أبداً)

### 4. جرّب رفع فيديو تجريبي محلياً (اختياري بس موصى فيه)
```bash
python scripts/youtube_upload.py \
  --file test.mp4 \
  --title "Test Upload" \
  --privacy private
```
لو نجح، معناها الإعداد صحيح 100% قبل ما تعتمد على GitHub Actions.

### 5. الاستخدام الفعلي (Workflow)
حط بمجلد `videos/to_upload/`:
- `episode.mp4` (الفيديو)
- `episode.json` (ميتاداتا - شوف `videos/to_upload/_TEMPLATE.json.example`)
- `episode_thumb.jpg` (اختياري، صورة مصغرة)

اعمل commit + push للمجلد `videos/to_upload/` على branch `main`.
الـ workflow بينفعل تلقائياً (`push` trigger)، وكمان في:
- تشغيل يومي احتياطي الساعة 09:00 UTC
- زر تشغيل يدوي من تبويب Actions ("Run workflow")

بعد الرفع: الفيديو والصورة المصغرة بيتحذفوا من المجلد (ما نخزن فيديوهات كبيرة بالـ git)،
والميتاداتا بتنتقل لـ `videos/uploaded/`، والـ manifest بيتحدث - كل هذا commit تلقائي من الـ bot.

## ملاحظات مهمة

- **Category ID الافتراضي = "1" (Film & Animation)**. لو محتواك تعليمي أكتر، جرب "27" (Education).
- **`made_for_kids: true`** بالميتاداتا - هذا مهم قانونياً (COPPA) لمحتوى أطفال، خلّيه دايماً true إذا كان الفيديو موجّه للأطفال.
- **حصة الـ API اليومية (quota)**: كل رفع فيديو بياخذ ~1600 نقطة من أصل 10,000 نقطة يومياً مجاناً، يعني تقدر ترفع حوالي 6 فيديوهات يومياً بدون طلب زيادة حصة. لو محتاج أكتر، فيه Google Cloud Console → APIs & Services → Quotas → طلب زيادة.
- **لو الـ token صار invalid** (مثلاً لو غيرت الباسورد أو سحبت الصلاحية من Google Account)، لازم تعيد الخطوة 2-3.

## الخطوة الجاية
لو بدك، أقدر:
- أضيف دعم لرفع لعدة قنوات يوتيوب بنفس الوقت
- أربط توليد الفيديو (من أدوات الـ AI المتوفرة) مباشرة بمجلد `videos/to_upload/` بشكل تلقائي كامل (من الفكرة للنشر بدون تدخل يدوي)
