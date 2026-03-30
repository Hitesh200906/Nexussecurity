// script.js – shared across all pages
document.addEventListener('DOMContentLoaded', () => {
    // Helper: update the auth button in navbar
    const updateAuthButton = () => {
        const container = document.getElementById('authButtonContainer');
        if (!container) return;
        const isLoggedIn = localStorage.getItem('nexusLoggedIn') === 'true';
        if (isLoggedIn) {
            container.innerHTML = `<a href="profile.html" id="authButton"><span>Profile</span></a>`;
        } else {
            container.innerHTML = `<a href="login.html" id="authButton"><span>Create account</span></a>`;
        }
    };
    updateAuthButton();

    // Get Started button – scroll to plans section
    const getStartedBtn = document.getElementById('heroGetStarted');
    if (getStartedBtn) {
        getStartedBtn.addEventListener('click', (e) => {
            e.preventDefault();
            document.getElementById('plans').scrollIntoView({ behavior: 'smooth' });
        });
    }

    // ========== PLAN SELECTION & FORM HANDLING ==========
    const planBtns = document.querySelectorAll('.plan-select-btn');
    const planSections = {
        basic: document.getElementById('urlSectionBasic'),
        advanced: document.getElementById('urlSectionAdvanced'),
        protection_plus: document.getElementById('urlSectionProtection')
    };
    let selectedPlan = null;

    const showUrlSection = (plan) => {
        selectedPlan = plan;
        // Hide all sections
        Object.values(planSections).forEach(section => {
            if (section) section.style.display = 'none';
        });
        // Show the selected one
        const targetSection = planSections[plan];
        if (targetSection) {
            targetSection.style.display = 'block';
            targetSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
            // Reset form fields in that section
            const form = targetSection.querySelector('form');
            if (form) form.reset();
        }
    };

    const hideUrlSection = () => {
        Object.values(planSections).forEach(section => {
            if (section) section.style.display = 'none';
        });
        selectedPlan = null;
    };

    if (planBtns.length) {
        planBtns.forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.preventDefault();
                const plan = btn.getAttribute('data-plan');
                const isLoggedIn = localStorage.getItem('nexusLoggedIn') === 'true';
                if (isLoggedIn) {
                    showUrlSection(plan);
                } else {
                    window.location.href = 'login.html';
                }
            });
        });
    }

    // ========== MODAL & MESSAGE BOX FUNCTIONS ==========
    // Ask a yes/no question with a modal
    function askQuestion(question) {
        return new Promise((resolve) => {
            const modal = document.getElementById('questionModal');
            const questionText = document.getElementById('questionText');
            const yesBtn = document.getElementById('modalYes');
            const noBtn = document.getElementById('modalNo');

            questionText.textContent = question;
            modal.style.display = 'flex';

            const onYes = () => {
                modal.style.display = 'none';
                cleanup();
                resolve(true);
            };
            const onNo = () => {
                modal.style.display = 'none';
                cleanup();
                resolve(false);
            };
            const cleanup = () => {
                yesBtn.removeEventListener('click', onYes);
                noBtn.removeEventListener('click', onNo);
            };
            yesBtn.addEventListener('click', onYes);
            noBtn.addEventListener('click', onNo);
        });
    }

    // Show a message box (toast) that auto‑hides after 5 seconds
    function showMessage(message, isError = false) {
        const box = document.getElementById('messageBox');
        const text = document.getElementById('messageText');
        text.textContent = message;
        box.style.display = 'flex';
        if (isError) {
            box.style.borderLeftColor = '#ef4444';
        } else {
            box.style.borderLeftColor = '#2f9b9b';
        }
        // Auto-hide after 5 seconds
        setTimeout(() => {
            box.style.display = 'none';
        }, 5000);
    }

    // Close message box manually
    const closeMsgBtn = document.getElementById('closeMessage');
    if (closeMsgBtn) {
        closeMsgBtn.addEventListener('click', () => {
            document.getElementById('messageBox').style.display = 'none';
        });
    }

    // ========== ATTACH SUBMIT HANDLERS TO ALL FORMS ==========
    const forms = document.querySelectorAll('.scan-form');
    forms.forEach(form => {
        form.addEventListener('submit', async (e) => {
            e.preventDefault();

            // Get plan from hidden input
            const planInput = form.querySelector('input[name="plan"]');
            const plan = planInput ? planInput.value : selectedPlan;

            // Gather all fields
            const fullName = form.querySelector('input[name="fullName"]')?.value.trim();
            const role = form.querySelector('input[name="role"]')?.value.trim();
            const companyName = form.querySelector('input[name="companyName"]')?.value.trim();
            const userEmail = form.querySelector('input[name="userEmail"]')?.value.trim();
            const websiteUrl = form.querySelector('input[name="websiteUrl"]')?.value.trim();
            const businessEmail = form.querySelector('input[name="businessEmail"]')?.value.trim();

            // Validate all required fields
            if (!fullName || !role || !companyName || !userEmail || !websiteUrl || !businessEmail) {
                showMessage('Please fill in all fields.', true);
                return;
            }

            // Validate URL format
            try {
                new URL(websiteUrl);
            } catch (_) {
                showMessage('Please enter a valid website URL (e.g., https://example.com).', true);
                return;
            }

            // Validate email formats
            if (!userEmail.includes('@') || !businessEmail.includes('@')) {
                showMessage('Please enter valid email addresses.', true);
                return;
            }

            // Disable submit button to prevent double submission
            const submitBtn = form.querySelector('button[type="submit"]');
            const originalBtnHTML = submitBtn.innerHTML;
            submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Verifying...';
            submitBtn.disabled = true;

            try {
                // --- AI Verification Phase ---
                // 1. Ask if the business email is mentioned on the website
                const isMentioned = await askQuestion(`Is the email address "${businessEmail}" mentioned anywhere on your website (${websiteUrl})?`);

                if (isMentioned) {
                    showMessage(`Checking your website for ${businessEmail}...`);
                    await new Promise(resolve => setTimeout(resolve, 2000)); // simulate scanning
                    showMessage(`✅ Great! We found ${businessEmail} on your website. Ownership verified.`);
                } else {
                    // 2. Send a verification email via backend
                    showMessage(`Sending verification email to ${businessEmail}...`);
                    const sendRes = await fetch('/send_verification', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ email: businessEmail, website: websiteUrl, plan })
                    });
                    const sendData = await sendRes.json();
                    if (sendData.success) {
                        showMessage(`📧 Verification email sent to ${businessEmail}. Please click the link in your inbox to confirm.`);
                        // Optionally wait for user to confirm – you can add a "I've confirmed" button here
                    } else {
                        throw new Error(sendData.message || 'Failed to send email');
                    }
                }

                // --- Submit scan to backend ---
                let paymentId = null;
                const prices = { basic: 0, advanced: 99, protection_plus: 999 };
                if (prices[plan] > 0) {
                    const paymentRes = await fetch('/api/payment_mock', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ plan })
                    });
                    const paymentData = await paymentRes.json();
                    if (paymentData.success) paymentId = paymentData.payment_id;
                }

                const formData = new URLSearchParams();
                formData.append('url', websiteUrl);
                formData.append('plan', plan);
                if (paymentId) formData.append('payment_id', paymentId);

                const res = await fetch('/submit_scan', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                    body: formData
                });

                if (res.ok) {
                    showMessage(`✅ Scan request for ${websiteUrl} (${plan.toUpperCase()}) has been submitted. You will receive the report in your profile within 24 hours.`);
                    // Hide the section and reset
                    const parentSection = form.closest('.plan-url-section');
                    if (parentSection) parentSection.style.display = 'none';
                } else {
                    showMessage('❌ Submission failed. Please try again.', true);
                }
            } catch (error) {
                console.error('Submission error:', error);
                showMessage('An error occurred. Please try again later.', true);
            } finally {
                // Re-enable submit button
                submitBtn.innerHTML = originalBtnHTML;
                submitBtn.disabled = false;
            }
        });
    });

    // ========== LOGIN PAGE LOGIC ==========
    const loginTab = document.getElementById('loginTab');
    const signupTab = document.getElementById('signupTab');
    const loginFormDiv = document.getElementById('loginForm');
    const signupFormDiv = document.getElementById('signupForm');
    const doLogin = document.getElementById('doLogin');
    const doSignup = document.getElementById('doSignup');
    const googleLogin = document.getElementById('googleLogin');
    const googleSignup = document.getElementById('googleSignup');

    if (loginTab && signupTab && loginFormDiv && signupFormDiv) {
        const setActiveTab = (active) => {
            if (active === 'login') {
                loginTab.classList.add('active');
                signupTab.classList.remove('active');
                loginFormDiv.classList.add('active');
                signupFormDiv.classList.remove('active');
            } else {
                signupTab.classList.add('active');
                loginTab.classList.remove('active');
                signupFormDiv.classList.add('active');
                loginFormDiv.classList.remove('active');
            }
        };
        loginTab.addEventListener('click', () => setActiveTab('login'));
        signupTab.addEventListener('click', () => setActiveTab('signup'));
    }

    if (doLogin) {
        doLogin.addEventListener('click', () => {
            const email = document.getElementById('loginEmail').value;
            const password = document.getElementById('loginPassword').value;
            if (!email || !password) {
                alert('Please fill in both fields.');
                return;
            }
            localStorage.setItem('nexusLoggedIn', 'true');
            localStorage.setItem('userName', email.split('@')[0]);
            localStorage.setItem('userEmail', email);
            alert('Logged in successfully!');
            window.location.href = 'index.html';
        });
    }

    if (doSignup) {
        doSignup.addEventListener('click', () => {
            const name = document.getElementById('signupName').value;
            const email = document.getElementById('signupEmail').value;
            const password = document.getElementById('signupPassword').value;
            if (!name || !email || !password) {
                alert('Please fill in all fields.');
                return;
            }
            localStorage.setItem('nexusLoggedIn', 'true');
            localStorage.setItem('userName', name);
            localStorage.setItem('userEmail', email);
            alert('Account created! You are now logged in.');
            window.location.href = 'index.html';
        });
    }

    const handleGoogleLogin = () => {
        localStorage.setItem('nexusLoggedIn', 'true');
        localStorage.setItem('userName', 'Google User');
        localStorage.setItem('userEmail', 'user@gmail.com');
        alert('Logged in with Google (demo).');
        window.location.href = 'index.html';
    };
    if (googleLogin) googleLogin.addEventListener('click', handleGoogleLogin);
    if (googleSignup) googleSignup.addEventListener('click', handleGoogleLogin);

    // ========== PROFILE PAGE LOGIC ==========
    const profileName = document.getElementById('profileName');
    const profileEmail = document.getElementById('profileEmail');
    const logoutBtn = document.getElementById('logoutBtn');
    if (profileName && profileEmail) {
        profileName.textContent = localStorage.getItem('userName') || 'User';
        profileEmail.textContent = localStorage.getItem('userEmail') || 'user@example.com';
        const scanHistory = JSON.parse(localStorage.getItem('scanHistory')) || [];
        const historyContainer = document.getElementById('scanHistoryList');
        if (historyContainer) {
            if (scanHistory.length === 0) {
                historyContainer.innerHTML = '<p class="no-scans">No scans yet. Start a scan from the home page.</p>';
            } else {
                historyContainer.innerHTML = scanHistory.map(scan => `
                    <div class="scan-item">
                        <strong>${scan.plan.toUpperCase()}</strong> – ${scan.url}<br>
                        <small>Submitted: ${new Date(scan.date).toLocaleString()}</small>
                    </div>
                `).join('');
            }
        }
    }

    if (logoutBtn) {
        logoutBtn.addEventListener('click', () => {
            localStorage.removeItem('nexusLoggedIn');
            localStorage.removeItem('userName');
            localStorage.removeItem('userEmail');
            window.location.href = 'index.html';
        });
    }
});