# Twilio Setup Guide for Real SMS

## 🎯 Quick Steps

### 1. Get Your Twilio Credentials

**Option A: New Twilio Account**
1. Visit https://www.twilio.com/console
2. Sign up for a free Twilio account
3. Verify your phone number
4. Get a trial phone number (US/Ghana/Other)

**Option B: Existing Twilio Account**
1. Go to https://www.twilio.com/console
2. Log in to your account

### 2. Find Your Credentials

**In Twilio Console Dashboard:**
```
Account SID: Look on main dashboard (starts with AC)
Auth Token: Look on main dashboard  
Phone Number: Go to Phone Numbers → Active Numbers
```

### 3. Update Django Settings

**File:** `E_Commence/settings.py`

**Find these lines (around line 185-190):**
```python
TWILIO_ACCOUNT_SID = 'your_real_account_sid_here'
TWILIO_AUTH_TOKEN = 'your_real_auth_token_here'
TWILIO_PHONE_NUMBER = 'your_real_twilio_phone_number'
```

**Replace with your actual credentials:**
```python
TWILIO_ACCOUNT_SID = 'ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'  # Your Account SID from console
TWILIO_AUTH_TOKEN = 'your_long_token_string_from_console'  # Your Auth Token
TWILIO_PHONE_NUMBER = '+233551234567'  # Your Twilio phone number (E.164 format)
```

### 4. Format Your Phone Number

**Important:** Phone number must be in E.164 format:
- ✅ Correct: `+233551234567` (country code + number)
- ✅ Correct: `+12025551234` (US example)
- ❌ Wrong: `0551234567` (missing country code)
- ❌ Wrong: `551234567` (missing + sign)

### 5. Verify it Works

**Restart Django server:**
```bash
# Stop current server (Ctrl+C)
# Then restart:
python manage.py runserver
```

**Check logs for success message:**
```
✓ Twilio client initialized successfully
```

### 6. Send a Test SMS

1. Go to Admin Dashboard: http://localhost:8000/admin
2. Click Notifications → Send Bulk Notification
3. Select a user, SMS template, and send
4. Check your phone!

---

## 🔍 Troubleshooting

### Error: "Authentication Error - invalid username"
- ❌ Credentials are wrong or invalid
- ✅ Solution: Copy-paste directly from Twilio console (don't type manually)

### SMS Not Received
- ✅ Check SMS Logs in admin: `/admin/notifications/smslog/`
- ✅ Look for status "sent" with provider "twilio"
- Check Twilio console for delivery status

### Still in Development Mode?
- Run: `python manage.py shell`
- Then: 
  ```python
  from notifications.services import NotificationService
  s = NotificationService()
  print(f'Twilio Enabled: {s.twilio_enabled}')
  ```
- Should show: `Twilio Enabled: True`

---

## 💡 Twilio Trial Account Info

**Free Trial includes:**
- 15 free account credit ($)
- Send SMS to verified numbers
- Receive SMS on trial number

**Twilio Phone Costs:**
- $1-2 per month to keep phone number
- $0.0075 per SMS sent (varies by country)

---

## 📚 Useful Links

- Twilio Console: https://www.twilio.com/console
- Phone Number Format: https://www.twilio.com/docs/glossary/what-e164
- Twilio Pricing: https://www.twilio.com/sms/pricing

---

## ✅ Configuration Checklist

- [ ] Created Twilio account
- [ ] Got Account SID
- [ ] Got Auth Token
- [ ] Got Twilio phone number
- [ ] Updated settings.py with real credentials
- [ ] Restarted Django server
- [ ] Verified "Twilio client initialized successfully" in logs
- [ ] Tested sending SMS
- [ ] Received SMS on phone

