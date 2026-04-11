// script.js – Nexus Security (Professional Dual Verification)
document.addEventListener('DOMContentLoaded', () => {
    if (typeof fetch === 'undefined') {
        console.error('fetch() is not supported. Please update your browser.');
        return;
    }

    // ---------- Modal message for selected messages ----------
    const modalMessagesList = [
        "Please choose a verification method.",
        "Could not reach website",
        "Could not find",
        "Verification email sent to",
        "Verification code generated!",
        "Missing verification data. Please start again.",
        "Code expired. Please request a new scan.",
        "Code \"",
        "✅ Verification successful!",
        "Scan started! You will receive the report on your profile page.",
        "No scans yet. Start a scan from the home page.",
        "Report is not ready yet. Please check back later."
    ];

    function showModalMessage(message, isError = false, onClose = null) {
        const existingOverlay = document.querySelector('.modal-message-overlay');
        if (existingOverlay) existingOverlay.remove();

        const overlay = document.createElement('div');
        overlay.className = 'modal-message-overlay';
        const card = document.createElement('div');
        card.className = 'modal-message-card';
        const icon = isError ? '<i class="fas fa-exclamation-triangle"></i>' : '<i class="fas fa-check-circle"></i>';
        const title = isError ? 'Error' : 'Success';
        card.innerHTML = `
            ${icon}
            <h3>${title}</h3>
            <p>${message}</p>
            <button class="modal-message-button">Got it</button>
        `;
        overlay.appendChild(card);
        document.body.appendChild(overlay);

        const closeBtn = card.querySelector('.modal-message-button');
        const closeModal = () => {
            overlay.remove();
            if (onClose) onClose();
        };
        closeBtn.addEventListener('click', closeModal);
        overlay.addEventListener('click', (e) => { if (e.target === overlay) closeModal(); });
    }

    function showToastMessage(message, isError = false) {
        const box = document.getElementById('messageBox');
        if (!box) return;
        const text = document.getElementById('messageText');
        text.textContent = message;
        box.style.display = 'flex';
        box.style.borderLeftColor = isError ? '#ef4444' : '#2f9b9b';
        setTimeout(() => { box.style.display = 'none'; }, 5000);
    }

    function showMessage(message, isError = false, onClose = null) {
        let useModal = false;
        for (let pattern of modalMessagesList) {
            if (message.includes(pattern) || message.startsWith(pattern)) {
                useModal = true;
                break;
            }
        }
        if (useModal) {
            showModalMessage(message, isError, onClose);
        } else {
            showToastMessage(message, isError);
        }
    }

    // ---------- Update auth button ----------
    async function updateAuthButton() {
        const container = document.getElementById('authButtonContainer');
        if (!container) return;
        try {
            const response = await fetch('/api/status');
            const data = await response.json();
            if (data.logged_in) {
                container.innerHTML = `<a href="/profile" id="authButton"><span>Profile</span></a>`;
            } else {
                container.innerHTML = `<a href="/login.html" id="authButton"><span>Create account</span></a>`;
            }
        } catch (err) {
            console.error('Auth status check failed:', err);
            container.innerHTML = `<a href="/login.html" id="authButton"><span>Create account</span></a>`;
        }
    }
    updateAuthButton();

    // ---------- Login / Signup (unchanged) ----------
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
        doLogin.addEventListener('click', async () => {
            const email = document.getElementById('loginEmail').value.trim();
            const password = document.getElementById('loginPassword').value;
            if (!email || !password) {
                showMessage('Please fill in both fields.', true);
                return;
            }
            const btn = doLogin;
            const originalHTML = btn.innerHTML;
            btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Logging in...';
            btn.disabled = true;
            try {
                const response = await fetch('/api/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email, password })
                });
                const data = await response.json();
                if (response.ok && data.success) {
                    showMessage('✅ Login successful! Redirecting...');
                    setTimeout(() => {
                        window.location.href = '/index.html?t=' + Date.now();
                    }, 1000);
                } else {
                    showMessage(data.message || 'Login failed. Please try again.', true);
                    btn.innerHTML = originalHTML;
                    btn.disabled = false;
                    if (data.message && data.message.includes('No account found') && signupTab) {
                        signupTab.click();
                    }
                }
            } catch (error) {
                console.error('Login error:', error);
                showMessage('Network error. Please check your connection.', true);
                btn.innerHTML = originalHTML;
                btn.disabled = false;
            }
        });
    }

    if (doSignup) {
        doSignup.addEventListener('click', async () => {
            const name = document.getElementById('signupName').value.trim();
            const email = document.getElementById('signupEmail').value.trim();
            const password = document.getElementById('signupPassword').value;
            const confirm = document.getElementById('signupConfirmPassword').value;
            if (!name || !email || !password) {
                showMessage('Please fill in all fields.', true);
                return;
            }
            if (password !== confirm) {
                showMessage('Passwords do not match.', true);
                return;
            }
            const btn = doSignup;
            const originalHTML = btn.innerHTML;
            btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Signing up...';
            btn.disabled = true;
            try {
                const response = await fetch('/api/register', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name, email, password })
                });
                const data = await response.json();
                if (response.ok && data.success) {
                    showMessage('✅ Account created! You are now logged in. Redirecting...');
                    setTimeout(() => {
                        window.location.href = '/index.html?t=' + Date.now();
                    }, 1000);
                } else {
                    showMessage(data.message || 'Registration failed.', true);
                    btn.innerHTML = originalHTML;
                    btn.disabled = false;
                }
            } catch (error) {
                console.error('Registration error:', error);
                showMessage('An error occurred. Please try again.', true);
                btn.innerHTML = originalHTML;
                btn.disabled = false;
            }
        });
    }

    // ✅ CHANGED: Google login now redirects to Supabase OAuth endpoint
    const handleGoogle = () => {
        window.location.href = '/login/google';
    };
    if (googleLogin) googleLogin.addEventListener('click', handleGoogle);
    if (googleSignup) googleSignup.addEventListener('click', handleGoogle);

    // ---------- Plan selection ----------
    const planBtns = document.querySelectorAll('.plan-select-btn');
    const planSections = {
        basic: document.getElementById('urlSectionBasic'),
        advanced: document.getElementById('urlSectionAdvanced'),
        protection_plus: document.getElementById('urlSectionProtection')
    };
    let selectedPlan = null;

    const showUrlSection = (plan) => {
        selectedPlan = plan;
        Object.values(planSections).forEach(section => {
            if (section) section.style.display = 'none';
        });
        const targetSection = planSections[plan];
        if (targetSection) {
            targetSection.style.display = 'block';
            targetSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
            const form = targetSection.querySelector('.scan-form');
            if (form) form.reset();
            // Reset UI elements
            const manualPanel = targetSection.querySelector('.manual-code-panel');
            if (manualPanel) manualPanel.style.display = 'none';
            const startBtn = targetSection.querySelector('.start-scan-btn');
            if (startBtn) {
                startBtn.disabled = true;
                startBtn.textContent = 'Select verification method first';
                startBtn.style.display = 'block';
            }
            const existingStartNow = targetSection.querySelector('.start-scan-now-btn');
            if (existingStartNow) existingStartNow.remove();
            delete form?.dataset.verificationId;
            delete form?.dataset.websiteUrl;
            delete form?.dataset.jobId;
            delete form?.dataset.verified;
        }
    };

    if (planBtns.length) {
        planBtns.forEach(btn => {
            btn.addEventListener('click', async (e) => {
                e.preventDefault();
                const plan = btn.getAttribute('data-plan');
                try {
                    const statusRes = await fetch('/api/status');
                    const status = await statusRes.json();
                    if (status.logged_in) {
                        showUrlSection(plan);
                    } else {
                        window.location.href = 'login.html';
                    }
                } catch {
                    window.location.href = 'login.html';
                }
            });
        });
    }

    // ---------- Close message button (for toast) ----------
    const closeMsgBtn = document.getElementById('closeMessage');
    if (closeMsgBtn) {
        closeMsgBtn.addEventListener('click', () => {
            document.getElementById('messageBox').style.display = 'none';
        });
    }

    // ---------- SCAN FORM HANDLER (Dual verification) ----------
    const forms = document.querySelectorAll('.scan-form');
    forms.forEach(form => {
        const methodRadios = form.querySelectorAll('input[name="emailOnSite"]');
        const startBtn = form.querySelector('.start-scan-btn');
        const manualPanel = form.querySelector('.manual-code-panel');
        const verifyBtn = form.querySelector('.verify-code-btn');
        const copyBtn = form.querySelector('.copy-code-btn');
        const codeSpan = form.querySelector('.verification-code');
        const verifyStatusDiv = form.querySelector('.verify-status');

        // Enable start button when a verification method is selected
        methodRadios.forEach(radio => {
            radio.addEventListener('change', () => {
                if (radio.checked) {
                    startBtn.disabled = false;
                    startBtn.textContent = 'Start Scan';
                    startBtn.style.display = 'block';
                    if (radio.value === 'yes' && manualPanel) {
                        manualPanel.style.display = 'none';
                    }
                }
            });
        });

        // Start Scan button click (first step: generate code or send email)
        startBtn.addEventListener('click', async () => {
            if (startBtn.disabled) return;

            // If this form has already been verified (manual code flow), then this click means "start the scan"
            if (form.dataset.verified === 'true') {
                showMessage('Scan started! You will receive the report on your profile page.');
                startBtn.disabled = true;
                startBtn.textContent = 'Scan Started';
                return;
            }

            const selectedRadio = form.querySelector('input[name="emailOnSite"]:checked');
            if (!selectedRadio) {
                showMessage('Please choose a verification method.', true);
                return;
            }
            const emailOnSite = selectedRadio.value;

            // Gather form data
            const fullName = form.querySelector('[name="fullName"]').value.trim();
            const role = form.querySelector('[name="role"]').value.trim();
            const companyName = form.querySelector('[name="companyName"]').value.trim();
            const userEmail = form.querySelector('[name="userEmail"]').value.trim();
            const websiteUrl = form.querySelector('[name="websiteUrl"]').value.trim();
            const businessEmail = form.querySelector('[name="businessEmail"]').value.trim();
            const plan = form.getAttribute('data-plan') || selectedPlan;

            if (!fullName || !role || !companyName || !userEmail || !websiteUrl || !businessEmail) {
                showMessage('Please fill all fields.', true);
                return;
            }
            try { new URL(websiteUrl); } catch (_) {
                showMessage('Invalid website URL.', true);
                return;
            }

            startBtn.disabled = true;
            startBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Processing...';

            const formData = new FormData();
            formData.append('fullName', fullName);
            formData.append('role', role);
            formData.append('companyName', companyName);
            formData.append('userEmail', userEmail);
            formData.append('websiteUrl', websiteUrl);
            formData.append('businessEmail', businessEmail);
            formData.append('plan', plan);
            formData.append('emailOnSite', emailOnSite);

            try {
                const response = await fetch('/api/request_scan', {
                    method: 'POST',
                    body: formData
                });
                const data = await response.json();

                if (!data.success) {
                    showMessage(data.message || 'Request failed', true);
                    startBtn.disabled = false;
                    startBtn.innerHTML = 'Start Scan';
                    return;
                }

                if (emailOnSite === 'yes') {
                    // Email flow: show message and hide the section
                    showMessage(data.message);
                    const parentSection = form.closest('.plan-url-section');
                    if (parentSection) parentSection.style.display = 'none';
                } else {
                    // Manual code flow
                    showMessage('Verification code generated! Copy and paste it on your website.');
                    if (codeSpan) codeSpan.textContent = data.code;
                    if (manualPanel) manualPanel.style.display = 'block';
                    form.dataset.verificationId = data.token;
                    form.dataset.websiteUrl = websiteUrl;
                    startBtn.disabled = true;
                    startBtn.textContent = 'Waiting for code verification...';
                }
            } catch (err) {
                console.error(err);
                showMessage('Network error', true);
                startBtn.disabled = false;
                startBtn.innerHTML = 'Start Scan';
            }
        });

        // Verify Code button (manual path)
        if (verifyBtn) {
            verifyBtn.addEventListener('click', async () => {
                const verificationId = form.dataset.verificationId;
                const websiteUrl = form.dataset.websiteUrl;
                if (!verificationId || !websiteUrl) {
                    showMessage('Missing verification data. Please start again.', true);
                    return;
                }
                verifyBtn.disabled = true;
                verifyBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Verifying...';
                try {
                    const res = await fetch('/api/verify_code', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ verification_id: verificationId, website_url: websiteUrl })
                    });
                    const data = await res.json();
                    if (data.success) {
                        showMessage('✅ Verification successful! You can now start the scan.', false, () => {
                            window.location.href = '/profile';
                        });
                        if (verifyStatusDiv) verifyStatusDiv.innerHTML = '<span style="color:#2f9b9b;">✓ ' + data.message + '</span>';
                        manualPanel.style.display = 'none';
                        startBtn.disabled = false;
                        startBtn.textContent = 'Start Scan';
                        startBtn.style.display = 'block';
                        form.dataset.verified = 'true';
                        const existingStartNow = form.parentElement?.querySelector('.start-scan-now-btn');
                        if (existingStartNow) existingStartNow.remove();
                        setTimeout(() => {
                            window.location.href = '/profile';
                        }, 3000);
                    } else {
                        showMessage(data.message, true);
                        verifyBtn.disabled = false;
                        verifyBtn.innerHTML = 'Verify Code';
                    }
                } catch (err) {
                    showMessage('Verification failed: ' + err.message, true);
                    verifyBtn.disabled = false;
                    verifyBtn.innerHTML = 'Verify Code';
                }
            });
        }

        // Copy code button
        if (copyBtn && codeSpan) {
            copyBtn.addEventListener('click', () => {
                navigator.clipboard.writeText(codeSpan.textContent);
                showMessage('Code copied to clipboard!');
            });
        }
    });
});
