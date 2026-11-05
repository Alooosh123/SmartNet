import os
import logging
from typing import Optional, Dict, Any
from config.settings import settings

logger = logging.getLogger(__name__)


def generate_reply(user: str, message: str, plan: str = "monthly") -> Dict[str, Any]:
    """Generate an AI or contextual reply to client inquiries based on their subscription tier."""
    api_key = settings.OPENAI_API_KEY or os.environ.get('OPENAI_API_KEY')
    msg_clean = message.strip()

    if not api_key:
        lower = msg_clean.lower()
        if any(k in lower for k in ['صلاحيات', 'صلاحياتي', 'مميزات باقتي', 'باقتي']):
            if plan == "annual":
                text = f"🌟 أهلاً {user}! أنت مشترك في **الباقة السنوية ($100 - VIP)**. صلاحياتك الحصرية تشمل:\n1. أمر إعادة تشغيل شبكة الراوتر (Reboot) مباشرة من الدردشة أو زر التحكم.\n2. استخدام الشات بوت الاحترافي وتنفيذ الأوامر الذكية.\n3. إدارة وفصل المستخدمين النشطين.\n4. توليد وطباعة الكروت بدون أي قيود."
            elif plan == "semi_annual":
                text = f"✨ أهلاً {user}! أنت مشترك في **الباقة النصف سنوية ($60)**. صلاحياتك تشمل:\n1. توليد وطباعة حتى 100 كرت عبر الدردشة مباشرة.\n2. فصل الجلسات والمستخدمين النشطين.\n3. شات بوت ذكي متقدم لتشخيص مشاكل الشبكة.\n💡 ملاحظة: إعادة تشغيل الشبكة حصرية للباقة السنوية."
            else:
                text = f"ℹ️ أهلاً {user}! أنت مشترك في **الباقة الشهرية ($20)**. باقتك تشمل:\n1. استعلامات الشات بوت الأساسية والدعم الفني.\n2. متابعة حالة الاتصال والاستهلاك.\n💡 للتمتع بصلاحيات إعادة تشغيل الراوتر وفصل المستخدمين وتوليد الكروت، يمكنك الترقية إلى الباقة النصف سنوية أو السنوية."
        elif any(k in lower for k in ['فحص سرعة', 'سرعة الشبكة', 'قياس السرعة']):
            text = f"📊 شبكة {settings.SSID} متصلة وتعمل بكفاءة. متوسط السرعة المتاحة للمشتركين يتراوح بين 5 إلى 20 ميجابت/ثانية حسب الباقة المشترك بها. إذا شعرت ببطء، تأكد من إيقاف أي تنزيلات بالخلفية."
        elif any(k in lower for k in ['رصيد', 'انتهاء', 'صلاحية', 'استعلام عن الرصيد']):
            text = f"💳 أهلاً {user}، لمعرفة تفاصيل رصيدك ووقت انتهاء الصلاحية بدقة، يمكنك فتح صفحة الدخول بالمتصفح، أو مراجعة معلومات حسابك باللوحة. صلاحية الاشتراك تبدأ تلقائياً من أول تسجيل دخول بالكرت."
        elif any(k in lower for k in ['شحن', 'طريقة شحن', 'كارت', 'كرت', 'كروت']):
            text = "⚡ طريقة الشحن سهلة جداً:\n1. اتصل بشبكة الواي فاي SmartNet-WiFi.\n2. افتح المتصفح وستظهر لك صفحة تسجيل الدخول تلقائياً.\n3. أدخل اسم المستخدم وكلمة المرور المكتوبة على الكرت أو امسح رمز الـ QR مباشرة بكاميرا هاتفك."
        elif any(k in lower for k in ['تجديد', 'اشتراك شهري', 'طلب تجديد']):
            text = "🔄 لتجديد اشتراكك، يمكنك تقديم طلب تجديد من خلال لوحة التحكم أو التواصل مع صاحب الشبكة وسيتم تمديد حسابك فور تأكيد الدفع عبر بوت المصادقة الآلي."
        elif any(k in lower for k in ['بطيء', 'تقطيع', 'ضعيف', 'مشكلة الاتصال', 'فصل']):
            text = "⚠️ خطوات سريعة لحل مشكلة التقطيع:\n1. قم بإيقاف تشغيل الواي فاي في هاتفك ثم أعد تشغيله.\n2. اقترب من أقرب نقطة بث (Access Point).\n3. تأكد من عدم اتصال أكثر من جهاز بنفس الكرت إن كانت باقتك لجهاز واحد."
        elif any(k in lower for k in ['باقة', 'باقات', 'أسعار', 'فئات']):
            text = "📦 باقات SmartNet المتوفرة حالياً:\n• **شهري**: 20 دولار (30 يوماً) - دعم فني واستعلامات أساسية.\n• **نصف سنة**: 60 دولار (180 يوماً - وفر 50%) - توليد كروت وفصل مستخدمين وشات بوت متقدم.\n• **سنوي**: 100 دولار (365 يوماً - الخيار الأفضل VIP) - صلاحية إعادة تشغيل الشبكة وتحكم كامل بدون قيود."
        elif any(k in lower for k in ['شبكة', 'واي فاي', 'wifi', 'اتصال']):
            text = f"شبكة {settings.SSID} تعمل بصورة طبيعية ومستقرة، وموزعة على نقاط وصول متعددة لتغطية كافة أرجاء المنطقة."
        elif any(k in lower for k in ['أمنية', 'تمنى', 'تمنيت', 'اقتراح']):
            text = f"شكراً لمشاركتنا اقتراحك: '{msg_clean}'. سنحرص على دراسته وتطوير النظام لتحقيق أفضل تجربة."
        else:
            text = f"مرحباً بك {user} (باقتك: {plan})، استلمنا رسالتك: '{msg_clean}'. يمكنك أيضاً استخدام الاقتراحات السريعة أعلاه للحصول على إجابة فورية!"
        
        return {'text': text, 'model': 'smartnet-assistant-v2', 'meta': {'plan': plan}}

    # Call OpenAI if key is available
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model='gpt-3.5-turbo',
            messages=[
                {
                    'role': 'system',
                    'content': f'أنت المساعد الذكي لنظام SmartNet لإدارة شبكات الإنترنت. العميل الحالي: {user}، باقة اشتراكه: {plan}. أجب بلباقة ولغة عربية واضحة ومختصرة ومفيدة مع مراعاة صلاحيات باقته.'
                },
                {'role': 'user', 'content': msg_clean}
            ],
            max_tokens=250,
            temperature=0.6,
        )
        reply_content = response.choices[0].message.content.strip()
        return {'text': reply_content, 'model': 'gpt-3.5-turbo', 'meta': {'id': response.id, 'plan': plan}}
    except Exception as e:
        logger.warning(f"OpenAI completion error: {e}")
        return {
            'text': f"مرحباً {user}، تم استلام استفسارك وسيتابع معك فريق الدعم قريباً.",
            'model': 'fallback',
            'meta': {'error': str(e)}
        }

