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

لتشغيل بناء النماذج الأساسية دفعة واحدة (الخصائص، توقع النقاط، تصنيف المرشحين، ملفات اللاعبين، وCF إذا كان سجل اختيارات الفرق موجودًا)، من جذر المشروع شغّل:

```powershell
py scripts\train_all_models.py --skip-slow-evaluations
```

لتشغيل التقييمات الزمنية الأبطأ أيضًا، احذف `--skip-slow-evaluations`. سيشغّل ذلك تقييم المواسم، مقارنة التوصيات، محاكاة الانتقالات، وتجربة وكيل RL. يمكن تشغيل أي سكريبت منفردًا عند الحاجة. بعد اعتماد FPL نتائج جولة جديدة، حدّث سجل الجولات أولًا باستخدام `py scripts\collect_training_data.py`، ثم أعد تشغيل خط التدريب. هذا نموذج أولي للمقارنة والتعلّم؛ لا تعتمد على RL أو توصيات CF كاستراتيجية مؤكدة.

بعد التدريب الأساسي، يمكن إعادة تشغيل التقييمات فقط دون إعادة التدريب باستخدام `py scripts\train_all_models.py --evaluations-only`. المقاييس الحالية: التنبؤ فاق خط أساس آخر 3 جولات في 4 مواسم متتابعة (متوسط MAE للنموذج 1.032 مقابل 1.0862 للخط الأساس). في المقابل، وكيل RL سجل 1657 مقابل 1786 نقطة للاحتفاظ في اختبار 2024/25، و1731 مقابل 1757 في 2025/26؛ لذلك لا يُستخدم لاتخاذ قرارات آلية.

لإعادة تقييم النموذج على نافذة زمنية متوسعة عبر المواسم الحديثة (مع إبقاء كل موسم اختبار خارج التدريب)، شغّل `py scripts\evaluate_rolling_seasons.py`. يحفظ التقرير في `reports/rolling_season_evaluation.json`.

لمحاكاة سياسة انتقالات تاريخية، شغّل `py scripts\backtest_transfer_policy.py`. ولتدريب وكيل RL تجريبي (يتدرب على 2024/25 ويُختبر على 2025/26):

```powershell
py scripts\train_transfer_rl.py
```

تُحفظ نتائج الوكيل في `reports/transfer_rl_metrics.json`. يختار بين الاحتفاظ وأفضل ثلاثة تبديلات متوقعة، ونتائجه بحثية أولية وليست استراتيجية موسم موثوقة.

لتقييم ترتيب توصيات البدائل مقابل الفورم وحده على جولات لاحقة، شغّل السكريبت مع الموسم، مثل `py scripts\evaluate_hybrid_recommender.py 2025-26`. جرى التقييم على 3,360 استعلامًا في المواسم 2023/24–2025/26؛ متوسط نقاط أفضل خمسة بدائل كان 3.5457 لـ Hybrid و3.6974 للفورم وحده. لذلك يستخدم النظام تشابه Hybrid لكسر التعادل فقط، وتظل النقاط المتوقعة العامل الأساسي.

لإعادة جمع وتدريب CF من الترتيب العام واختباره مقابل خط أساس الشعبية، شغّل `py scripts\collect_user_picks.py --leaderboard-teams 50 --rounds 8` ثم `py scripts\train_collaborative_recommender.py`. القياس الحالي على 50 فريقًا و1610 تفاعلات أعطى Precision@10 = 0.03، مساويًا لخط أساس الشعبية؛ لذلك وزن CF محدود إلى 5% من إشارة كسر التعادل.

## تشغيل تطبيق الموبايل

يتطلب Node.js LTS وExpo Go على الهاتف.

```powershell
cd mobile
npm start
```

لو هتفتح التطبيق على هاتف فعلي، الكمبيوتر والهاتف يكونوا على نفس شبكة Wi-Fi. أنشئ ملف `mobile/.env` من `.env.example`، وضع عنوان IP المحلي للكمبيوتر بدل `<PC-LAN-IP>`، مثل `http://192.168.1.20:8000`. ثم أعد تشغيل Expo. على Android Emulator استخدم عادةً `http://10.0.2.2:8000`، وعلى iOS Simulator استخدم `http://127.0.0.1:8000`.

بعدها امسح QR الظاهر في الطرفية باستخدام Expo Go. وثائق Expo تشرح تشغيل خادم التطوير وفتح التطبيق على الهاتف أو المحاكي: https://docs.expo.dev/get-started/start-developing/.

## تشغيل نسخة الويب

الواجهة نفسها تعمل على الويب من خلال Expo. للتطوير محليًا شغّل `npm run web` من مجلد `mobile`. لبناء ملفات موقع ثابتة داخل `mobile/dist` شغّل:

```powershell
cd mobile
npm run build:web
```

قيمة `EXPO_PUBLIC_API_URL` تُضمّن داخل ملفات الويب وقت البناء. ملف `mobile/.env` الحالي يشير إلى عنوان الكمبيوتر المحلي `http://192.168.1.8:8000`، لذلك تعمل النسخة على نفس شبكة Wi-Fi فقط. قبل نشر الموقع للعامة، غيّر القيمة إلى رابط HTTPS عام لخادم الـ API ثم أعد بناء الويب. نشر الواجهة وحدها لا يجعل الـ API المحلي متاحًا خارج الشبكة.

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

## حالة المشروع والخطوات التشغيلية

- اكتمل النموذج الأولي لتوقع نقاط الجولة التالية، وتصنيف المرشحين، وتجميع ملفات اللاعبين، وكشف الحالات الشاذة، وتوصيات البدلاء، وتحسين التشكيلة والانتقالات.
- أضيفت تقييمات زمنية لتوقع النقاط والتوصيات ومحاكاة الانتقالات. توصيات Hybrid أقل من الفورم وحده، وسياسة الانتقال البسيطة خسرت 89 نقطة أمام الاحتفاظ، ونتائج CF ووكيل RL لم تتفوق بشكل موثوق على خطوط الأساس.
- لتحديث البيانات بعد جولة مكتملة: `py scripts\collect_training_data.py`، ثم شغّل `py scripts\train_all_models.py` من جذر المشروع.
- بيانات CF مصدرها اختيارات عامة مجمعة؛ إذا لم يوجد `data/processed/user_player_interactions.csv` يتخطى خط التدريب هذا الجزء. لجمعها، شغّل `py scripts\collect_user_picks.py --leaderboard-teams 50 --rounds 8` ثم أعد خط التدريب.
 - نشر الـ API العام ما زال يحتاج استضافة بعنوان HTTPS. الوصول إلى AWS يعتمد على الحساب والـ profile المستخدمين في AWS CLI؛ يمكن استخدام تعليمات Render أعلاه كمسار بديل.

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

## نشر الخلفية على AWS

يتطلب المسار حساب AWS بصلاحيات ECR وApp Runner ووسيلة دفع إن طلبها الحساب. لا تضع مفاتيح AWS في ملفات المشروع أو المحادثة. لو أعددت حسابًا جديدًا، سجّل الدخول إليه عبر AWS CLI وأنشئ profile منفصلًا. مع AWS IAM Identity Center:

```powershell
aws configure sso --profile fantasyiq
aws sso login --profile fantasyiq
aws sts get-caller-identity --profile fantasyiq
```

تأكد أن `Account` في نتيجة الأمر هو رقم الحساب الجديد، ثم شغّل Docker Desktop وانتظر حتى يصبح المحرك جاهزًا. من جذر المشروع ارفع الصورة:

```powershell
.\scripts\push_to_ecr.ps1 -Region us-east-1 -Profile fantasyiq
```

في AWS Console افتح **App Runner → Create service**، واختر **Container registry → Amazon ECR** وحدد صورة `fantasyiq-api:latest`. أنشئ ECR access role عند طلبها، واضبط المنفذ `8000` وفحص الصحة `/api/health` ثم أنشئ الخدمة. اختبر `https://<domain>/api/health`، وضع نطاق الخدمة في `EXPO_PUBLIC_API_URL` داخل ملفي preview وproduction في `mobile/eas.json`. راجع تكاليف AWS قبل إنشاء App Runner؛ الرسوم تعتمد على الاستخدام.
