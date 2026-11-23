# FantasyIQ

تطبيق موبايل لتحليل Fantasy Premier League. النسخة الحالية تعرض بيانات اللاعبين وتساعد على اختيار تشكيلة من 15 لاعبًا حسب توقعات الجولة والميزانية وقيود FPL.

## شكل المشروع

- **Mobile:** Expo + React Native + TypeScript لتشغيل Android وiOS.
- **Backend:** FastAPI في Python لجلب البيانات وتقديمها للتطبيق وتشغيل مُحسّن التشكيلة.
- **Data:** نقطة `bootstrap-static` من واجهة FPL؛ يتجدد التخزين المؤقت كل 15 دقيقة.

قيمة xP في النسخة الحالية مصدرها موجز FPL، وليست توقعًا صادرًا عن نموذج FantasyIQ. سنضيف نماذجنا بعد حفظ بيانات الجولات التاريخية وتقييمها بتقسيم زمني.

## تشغيل الخلفية

يتطلب Python 3.11+ واتصالًا بالإنترنت.

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt
py -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

توثيق API المحلي: `http://127.0.0.1:8000/docs`.

### تشغيل الخلفية داخل Docker

من جذر المشروع:

```powershell
docker build -t fantasyiq-api .
docker run --rm -p 8000:8000 -e PORT=8000 fantasyiq-api
```

أو استخدم Docker Compose لإعادة البناء والتشغيل مع فحص صحة تلقائي:

```powershell
docker compose up --build -d
docker compose ps
docker compose logs -f fantasyiq-api
```

للإيقاف استخدم `docker compose down`.

تحقق من `http://localhost:8000/api/health`. عند النشر على منصة استضافة، وجّه التطبيق إلى عنوان HTTPS العام عبر `EXPO_PUBLIC_API_URL` في إعداد بناء Expo؛ لا تستخدم عنوان IP المحلي في نسخة التوزيع. صورة Docker تتضمن النماذج وسجل البيانات الحالي وتحليل ملفات اللاعبين. بيانات FPL المباشرة تحتاج اتصالًا خارجيًا وقت التشغيل.

## النموذج الأولي

تم تدريب نموذج `HistGradientBoostingRegressor` لتوقع نقاط اللاعب في الجولة التالية. التقسيم زمني: تحقق على موسم 2024/25 بعد التدريب على المواسم الأقدم، ثم اختبار نهائي على 2025/26 بعد التدريب حتى 2024/25. حقق الاختبار النهائي MAE = 1.0016 وRMSE = 1.9722، مقارنةً بـ MAE = 1.0602 وRMSE = 2.2039 لخط الأساس الذي يستخدم متوسط نقاط آخر 3 جولات. فحص 2026/27 الحالي منفصل عن التدريب والاختبار النهائي.

بعد حساب المقاييس، يعيد السكريبت تدريب ملف النشر على كل المواسم المكتملة حتى 2025/26. النموذج يجهز توقعات الجولة القادمة داخل API، والتطبيق يعرض توقع FantasyIQ بجانب توقع FPL. نقطة API: `GET /api/predictions`.

أضفت أيضًا مصنف Logistic Regression لاحتمال «مرشح قوي»: اللاعب الذي يتجاوز نقاطه في الجولة التالية الربع الأعلى التاريخي لمركزه. يظهر شريط «مرشح قوي» بجانب اللاعب عند احتمال 65% أو أكثر. نتائجه في `reports/high_potential_metrics.json`، ويعاد تدريبه بـ `py scripts\train_high_potential_classifier.py`.

شغّل `py scripts\train_next_gw_model.py` لإعادة التدريب وتحديث ملفات `models/` و`reports/`. بعد أن يؤكد FPL نتائج جولة جديدة، شغّل `py scripts\collect_training_data.py` لتحديث سجل الجولات؛ سيستخدم API أحدث جولة مكتملة عند طلب التوقعات. هذا نموذج أولي للمقارنة والتعلّم، وتبقى مراجعة تقسيم البيانات والخصائص خطوة مهمة قبل الاعتماد عليه.

لإعادة تقييم النموذج على نافذة زمنية متوسعة عبر المواسم الحديثة (مع إبقاء كل موسم اختبار خارج التدريب)، شغّل `py scripts\evaluate_rolling_seasons.py`. يحفظ التقرير في `reports/rolling_season_evaluation.json`.

## تشغيل تطبيق الموبايل

يتطلب Node.js LTS وExpo Go على الهاتف.

```powershell
cd mobile
npm start
```

لو هتفتح التطبيق على هاتف فعلي، الكمبيوتر والهاتف يكونوا على نفس شبكة Wi-Fi. أنشئ ملف `mobile/.env` من `.env.example`، وضع عنوان IP المحلي للكمبيوتر بدل `<PC-LAN-IP>`، مثل `http://192.168.1.20:8000`. ثم أعد تشغيل Expo. على Android Emulator استخدم عادةً `http://10.0.2.2:8000`، وعلى iOS Simulator استخدم `http://127.0.0.1:8000`.

بعدها امسح QR الظاهر في الطرفية باستخدام Expo Go. وثائق Expo تشرح تشغيل خادم التطوير وفتح التطبيق على الهاتف أو المحاكي: https://docs.expo.dev/get-started/start-developing/.

## تجهيز نسخة Android للتجربة عبر EAS

ملف `mobile/eas.json` يعرّف development وpreview APK وproduction. قبل البناء، استبدل `https://REPLACE_WITH_YOUR_PUBLIC_API_HOST` في الملف بعنوان HTTPS عام لخلفية FantasyIQ؛ عنوان `localhost` أو IP المنزل لن يعمل للمستخدمين خارج شبكتك. من مجلد `mobile` شغّل `npx eas-cli@latest build --platform android --profile preview`، ثم ثبّت APK الناتج من رابط EAS. يلزم تسجيل الدخول إلى Expo/EAS قبل البناء.

### نشر الـ API على Render

يوجد ملف `render.yaml` لتعريف خدمة Docker وفحص الصحة. ادفع المشروع إلى مستودع GitHub، ثم في Render اختر **New → Blueprint** واربط المستودع واقبل إنشاء خدمة `fantasyiq-api`. بعد اكتمال النشر انسخ عنوان HTTPS الذي يعرضه Render. ضع هذا العنوان مكان `https://REPLACE_WITH_YOUR_PUBLIC_API_HOST` في `mobile/eas.json`، ثم نفّذ أمر بناء EAS أعلاه. الخطة المجانية قد تدخل في وضع الخمول؛ أول طلب بعد الخمول قد يتأخر.

## نقاط API

- `GET /api/health` — حالة الخادم.
- `GET /api/overview` — ملخص الجولة واللاعبين والأندية.
- `GET /api/players?limit=700` — قائمة اللاعبين.
- `GET /api/predictions` — توقعات FantasyIQ للجولة التالية.
- `GET /api/squad?budget=100` — اقتراح تشكيلة.
- `GET /api/recommendations/transfers?player_id=60&budget=1&free_transfers=1&extra_transfers=2` — بدائل لاعب من مركزه مع صافي النقاط بعد خصم الانتقالات.
- `GET /api/recommendations/plan?player_ids=60,61&squad_ids=...&bank=1.5&free_transfers=1` — أفضل خطط استبدال حتى 5 لاعبين. أرسل `squad_ids` لكل لاعبي تشكيلتك الخمسة عشر حتى يتحقق الخادم من التشكيلة وقيد 3 لاعبين من النادي، وتُستخدم `bank` كرصيدك الحالي.
- `GET /api/analytics/player-profiles?limit=30` — مجموعات اللاعبين ودرجات الحالات الشاذة؛ أضف `anomalies_only=true` لإرجاع الحالات المرصودة فقط.

لإعادة بناء تحليل ملفات اللاعبين (K-Means وIsolation Forest) بعد تحديث البيانات:

```powershell
py scripts\train_player_profiles.py
```

يحفظ السكريبت النتائج في `reports/player_profiles.csv` والمقاييس في `reports/player_profile_metrics.json`. هذا تحليل وصفي لنهاية الموسم؛ الحالات الشاذة لا تعني إصابة أو توقعًا مؤكدًا.

## البيانات المجمعة

جمعنا بيانات جولات اللاعبين لمواسم 2016/17 حتى 2026/27 في `data/processed/player_gameweeks.csv.gz`، مع الاحتفاظ بالملفات الخام ومصدرها. لإعادة تحديث بيانات الموسم الحالي وإعادة بناء الملف الموحد:

```powershell
py scripts\collect_training_data.py
```

التفاصيل والمخطط والتحذيرات المنهجية في [data/README.md](data/README.md).

## خارطة الطريق

1. مراجعة الحقول وتجهيز الخصائص الزمنية من الجولات السابقة فقط.
2. جدول الخصائص والهدف للجولة التالية موجود في `data/processed/next_gw_training.csv.gz`، ويُعاد بناؤه بالأمر `py scripts\build_next_gw_features.py`.
3. تدريب baseline بسيط ثم مقارنة نماذج توقع نقاط الجولة التالية.
4. تقييم زمني بـ MAE وRMSE ومقارنة النموذج بتوقع FPL المنشور.
5. إضافة تصنيف اللاعبين وتجميعهم ورصد الحالات الشاذة مع أهداف تقييم واضحة.
6. تطوير التوصيات الشخصية ثم تحسين التشكيلة الأساسية والانتقالات.
7. إضافة قاعدة بيانات، وتوثيق، واختبارات، ونشر التطبيق والخلفية.
8. دراسة التعلم المعزز بعد بناء محاكي موسم وخطوط أساس قابلة للمقارنة.

## الملفات الرئيسية

```text
backend/main.py          FastAPI endpoints وتخزين مؤقت للبيانات
fantasyiq/data.py        جلب وتحويل بيانات FPL
fantasyiq/optimizer.py   تحسين تشكيلة 15 لاعبًا بقيود FPL
mobile/app/              مسارات Expo Router لشاشات التطبيق
mobile/App.tsx            مكونات وواجهة الشاشات
mobile/.env.example      إعداد رابط الخلفية
```

## فحوص التغييرات

ملف `.github/workflows/ci.yml` يشغّل فحص تركيب ملفات Python وExpo lint وTypeScript عند كل push أو pull request. شغّل الفحوص نفسها محليًا قبل التسليم:

```powershell
py -m py_compile backend\main.py fantasyiq\*.py scripts\*.py
cd mobile
npm ci
npm run lint
npx tsc --noEmit
```
