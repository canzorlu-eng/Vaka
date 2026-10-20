// DRAFT legal texts. Must be reviewed by a lawyer before launch.
// Each doc: { title, sections: [{h, p: [paragraphs], ul?: [items]}] }
const SELLER_TR = "[Satıcı unvanı / vergi no / adres / e-posta: DOLDURULACAK]";
const SELLER_EN = "[Seller legal name / tax no. / address / e-mail: TO BE FILLED]";

export const LEGAL = {
  tr: {
    banner: "TASLAK — Yayına almadan önce bir avukat tarafından gözden geçirilmelidir.",
    updated: "Son güncelleme: taslak",
    terms: {
      title: "Mesafeli Satış Sözleşmesi ve Kullanım Koşulları",
      sections: [
        { h: "1. Taraflar", p: [`Satıcı: ${SELLER_TR}`, "Alıcı: Vaka hizmetine Google hesabıyla kayıt olan ve ücretli plan satın alan kullanıcı."] },
        { h: "2. Hizmetin konusu", p: ["Vaka, diş hekimliği öğrencileri ve hekimler için sesli sanal hasta simülatörüdür. Ücretli (Pro) plan; daha yüksek aylık uygulama oturumu hakkı, doğal yapay zekâ hasta sesi, yapay zekâ ile vaka üretimi ve tam geçmiş erişimi sağlar.", "Vaka eğitim amaçlıdır; gerçek hastalar için tıbbi tavsiye, tanı veya tedavi yerine geçmez."] },
        { h: "3. Fiyat ve ödeme", p: ["Güncel fiyatlar Fiyatlandırma sayfasında gösterilir. Türkiye'de düzenlenen kartlar TL, yurt dışı kartlar USD ile tahsil edilir. Ödemeler iyzico altyapısıyla alınır; kart bilgileri Vaka tarafından saklanmaz.", "Abonelikler seçilen dönem (aylık/yıllık) sonunda otomatik yenilenir; dilediğiniz zaman Hesabım sayfasından yenilemeyi iptal edebilirsiniz."] },
        { h: "4. Cayma hakkı ve iptal", p: ["Cayma, iptal ve iade koşulları İptal ve İade Politikası sayfasında düzenlenmiştir. Dijital içerik / anında ifa edilen hizmetlerde yasal istisnalar saklıdır."] },
        { h: "5. Kullanıcı yükümlülükleri", ul: ["Hesabınızı üçüncü kişilerle paylaşmamak.", "Hizmeti otomatik araçlarla kötüye kullanmamak, adil kullanım limitlerini aşmamak.", "Sunulan içeriği izinsiz çoğaltmamak ve yeniden satmamak."] },
        { h: "6. Adil kullanım", p: ["Pro plandaki aylık oturum ve üretim limitleri adil kullanım esasına dayanır; kötüye kullanım halinde hizmet kısıtlanabilir."] },
        { h: "7. Sorumluluğun sınırlandırılması", p: ["Yapay zekâ tarafından üretilen içerik hatalı olabilir. Hizmet \"olduğu gibi\" sunulur; yasaların izin verdiği ölçüde dolaylı zararlardan sorumluluk kabul edilmez."] },
        { h: "8. Uyuşmazlık", p: ["Uyuşmazlıklarda Türkiye Cumhuriyeti kanunları uygulanır; tüketici hakem heyetleri ve tüketici mahkemeleri yetkilidir. [Ayrıntılar avukat tarafından tamamlanacaktır.]"] },
      ],
    },
    privacy: {
      title: "Gizlilik Bildirimi (KVKK / GDPR Aydınlatma Metni)",
      sections: [
        { h: "1. Veri sorumlusu", p: [`${SELLER_TR}`] },
        { h: "2. Hangi verileri saklıyoruz", ul: ["Google hesabınızdan: ad, e-posta adresi ve profil fotoğrafı.", "Uygulama içi: pratik oturumları ve konuşma kayıtları (transkript), puanlama raporları.", "Yapay zekâ kullanım bilgileri (aylık oturum/üretim sayıları, istek sayıları).", "Abonelik durumu. Kart bilgileri saklanmaz; iyzico tarafından işlenir."] },
        { h: "3. Amaç ve hukuki sebep", p: ["Hizmeti sunmak, hesabınızı yönetmek, kullanım limitlerini uygulamak, ödemeleri işlemek ve güvenliği sağlamak. Hukuki sebepler: sözleşmenin ifası, meşru menfaat ve yasal yükümlülükler."] },
        { h: "4. Veri işleyenler", ul: ["Google: oturum açma ve Gemini yapay zekâ modelleri.", "OpenAI: sesli yanıt (TTS) üretimi.", "iyzico: ödeme işlemleri.", "Render: barındırma (hosting)."], p: ["Verileriniz bu hizmet sağlayıcılara yalnızca hizmetin sunulması için aktarılır; yurt dışı aktarım olabilir."] },
        { h: "5. Saklama süresi", p: ["Pratik oturumları 180 gün sonra silinir. Hesabınızı sildiğinizde oturumlarınız ve raporlarınız kaldırılır. Yasal saklama yükümlülüğü olan fatura/ödeme kayıtları ilgili süre boyunca tutulur."] },
        { h: "6. Haklarınız", p: ["Verilerinize erişme, düzeltme, silme, taşıma (Hesabım > Verilerimi indir) ve itiraz haklarına sahipsiniz. Başvuru için yukarıdaki iletişim adresini kullanabilirsiniz."] },
        { h: "7. Çerezler", p: ["Yalnızca oturumu sürdürmek için gerekli çerez (vaka_session) kullanılır; reklam veya izleme çerezi kullanılmaz."] },
      ],
    },
    refund: {
      title: "İptal ve İade Politikası",
      sections: [
        { h: "Aylık plan", p: ["Dilediğiniz zaman iptal edebilirsiniz. İptal sonrası ödenen dönemin sonuna kadar Pro özelliklerine erişiminiz sürer; kısmi dönem iadesi yapılmaz. [TASLAK]"] },
        { h: "Yıllık plan", p: ["Satın alımdan sonra 14 gün içinde ve Pro özellikleri kullanılmamışsa tam iade talep edilebilir. 14 günden sonra iptal edilirse yenileme durdurulur ve erişim dönem sonuna kadar sürer. [TASLAK]"] },
        { h: "Nasıl başvurulur", p: ["İade talepleri için hesabınızdaki e-posta ile bize yazın: [DESTEK E-POSTASI: DOLDURULACAK]. İadeler orijinal ödeme yöntemine, iyzico üzerinden yapılır; bankanıza bağlı olarak birkaç iş günü sürebilir."] },
        { h: "Yasal haklar", p: ["Tüketicinin 6502 sayılı Kanun ve Mesafeli Sözleşmeler Yönetmeliği'nden doğan zorunlu hakları saklıdır."] },
      ],
    },
  },
  en: {
    banner: "DRAFT — must be reviewed by a lawyer before launch.",
    updated: "Last updated: draft",
    terms: {
      title: "Terms of Service and Distance Sales Agreement",
      sections: [
        { h: "1. Parties", p: [`Seller: ${SELLER_EN}`, "Buyer: a user who signs up with a Google account and purchases a paid plan."] },
        { h: "2. The service", p: ["Vaka is a voice-based virtual patient simulator for dental students and clinicians. The paid (Pro) plan provides a higher monthly practice-session allowance, a natural AI patient voice, AI-generated cases and full history.", "Vaka is for education only and is not medical advice, diagnosis or treatment for real patients."] },
        { h: "3. Pricing and payment", p: ["Current prices are shown on the Pricing page. Cards issued in Turkey are charged in TRY, international cards in USD. Payments are processed by iyzico; Vaka does not store card details.", "Subscriptions renew automatically at the end of the chosen period (monthly/yearly). You can turn off renewal at any time from My account."] },
        { h: "4. Withdrawal and cancellation", p: ["Withdrawal, cancellation and refund terms are set out in the Cancellation & Refund Policy. Statutory exceptions for digital content and immediately performed services apply."] },
        { h: "5. Your obligations", ul: ["Do not share your account with others.", "Do not abuse the service with automated tools or exceed fair-use limits.", "Do not copy or resell the content without permission."] },
        { h: "6. Fair use", p: ["Monthly session and generation limits on Pro are fair-use based; the service may be restricted in case of abuse."] },
        { h: "7. Limitation of liability", p: ["AI-generated content may contain errors. The service is provided \"as is\"; to the extent permitted by law we are not liable for indirect damages."] },
        { h: "8. Disputes", p: ["Turkish law applies; consumer arbitration boards and consumer courts have jurisdiction. [To be completed by counsel.]"] },
      ],
    },
    privacy: {
      title: "Privacy Notice (KVKK / GDPR)",
      sections: [
        { h: "1. Controller", p: [`${SELLER_EN}`] },
        { h: "2. What we store", ul: ["From your Google account: name, e-mail address and profile picture.", "In the app: practice sessions and conversation transcripts, scoring reports.", "AI usage data (monthly session/generation counts, request counts).", "Subscription status. Card data is never stored by us; it is handled by iyzico."] },
        { h: "3. Purpose and legal basis", p: ["To provide the service, manage your account, enforce usage limits, process payments and keep the service secure. Legal bases: performance of a contract, legitimate interests and legal obligations."] },
        { h: "4. Processors", ul: ["Google: sign-in and Gemini AI models.", "OpenAI: text-to-speech voice generation.", "iyzico: payment processing.", "Render: hosting."], p: ["Your data is shared with these providers only to deliver the service; transfers outside your country may occur."] },
        { h: "5. Retention", p: ["Practice sessions are deleted after 180 days. When you delete your account your sessions and reports are removed. Invoice/payment records subject to legal retention are kept for the required period."] },
        { h: "6. Your rights", p: ["You may access, correct, delete, port (My account > Download my data) and object to processing of your data. Use the contact address above to make a request."] },
        { h: "7. Cookies", p: ["Only the strictly necessary session cookie (vaka_session) is used; there are no advertising or tracking cookies."] },
      ],
    },
    refund: {
      title: "Cancellation & Refund Policy",
      sections: [
        { h: "Monthly plan", p: ["Cancel any time. After cancelling you keep Pro access until the end of the paid period; no partial-period refunds. [DRAFT]"] },
        { h: "Yearly plan", p: ["A full refund can be requested within 14 days of purchase if Pro features have not been used. After 14 days, cancelling stops renewal and access continues until the period ends. [DRAFT]"] },
        { h: "How to request", p: ["Write to us from your account e-mail: [SUPPORT E-MAIL: TO BE FILLED]. Refunds go back to the original payment method via iyzico and may take a few business days depending on your bank."] },
        { h: "Statutory rights", p: ["Mandatory consumer rights under applicable law (including Turkish Law No. 6502 and the Distance Contracts Regulation) are unaffected."] },
      ],
    },
  },
};
