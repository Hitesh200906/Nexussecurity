// script.js – shared across all pages
document.addEventListener('DOMContentLoaded', () => {
    // Helper: update the auth button in navbar based on server session
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
        doLogin.addEventListener('click', async () => {
            const email = document.getElementById('loginEmail').value.trim();
            const password = document.getElementById('loginPassword').value;

            if (!email || !password) {
                showMessage('Please fill in both fields.', true);
                return;
            }

            // Disable button to prevent multiple clicks
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

                if (data.success) {
                    showMessage('Logged in successfully!');
                    // Small delay to let the message show, then redirect
                    setTimeout(() => {
                        window.location.replace('index.html');
                    }, 500);
                } else {
                    showMessage(data.message || 'Login failed.', true);
                    btn.innerHTML = originalHTML;
                    btn.disabled = false;
                }
            } catch (error) {
                console.error('Login error:', error);
                showMessage('An error occurred. Please try again.', true);
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

            // Disable button
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

                if (data.success) {
                    showMessage('Account created! You are now logged in.');
                    setTimeout(() => {
                        window.location.replace('index.html');
                    }, 500);
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

    // Google login – redirects to Flask OAuth route
    const handleGoogle = () => {
        window.location.href = '/login';
    };
    if (googleLogin) googleLogin.addEventListener('click', handleGoogle);
    if (googleSignup) googleSignup.addEventListener('click', handleGoogle);

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
        Object.values(planSections).forEach(section => {
            if (section) section.style.display = 'none';
        });
        const targetSection = planSections[plan];
        if (targetSection) {
            targetSection.style.display = 'block';
            targetSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
            const form = targetSection.querySelector('form');
            if (form) form.reset();
        }
    };

    if (planBtns.length) {
        planBtns.forEach(btn => {
            btn.addEventListener('click', async (e) => {
                e.preventDefault();
                const plan = btn.getAttribute('data-plan');

                // Check if user is logged in before showing the form
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

    // ========== MODAL & MESSAGE BOX FUNCTIONS ==========
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
        setTimeout(() => {
            box.style.display = 'none';
        }, 5000);
    }

    const closeMsgBtn = document.getElementById('closeMessage');
    if (closeMsgBtn) {
        closeMsgBtn.addEventListener('click', () => {
            document.getElementById('messageBox').style.display = 'none';
        });
    }

    // ========== ATTACH SUBMIT HANDLERS TO ALL FORMS ==========
    const forms = document.querySelectorAll('.scan-form');
    forms.forEach(form => {
        // Toggle photo field based on radio selection
        const radioYes = form.querySelector('input[value="yes"]');
        const radioNo = form.querySelector('input[value="no"]');
        const photoGroup = form.querySelector('#photoGroup');

        if (radioYes && radioNo && photoGroup) {
            const togglePhoto = () => {
                photoGroup.style.display = radioNo.checked ? 'block' : 'none';
                const photoInput = form.querySelector('input[name="photo"]');
                if (photoInput) photoInput.required = radioNo.checked;
            };
            radioYes.addEventListener('change', togglePhoto);
            radioNo.addEventListener('change', togglePhoto);
            togglePhoto(); // initial state
        }

        form.addEventListener('submit', async (e) => {
            e.preventDefault();

            const planInput = form.querySelector('input[name="plan"]');
            const plan = planInput ? planInput.value : selectedPlan;

            // Gather all fields
            const fullName = form.querySelector('input[name="fullName"]')?.value.trim();
            const role = form.querySelector('input[name="role"]')?.value.trim();
            const companyName = form.querySelector('input[name="companyName"]')?.value.trim();
            const userEmail = form.querySelector('input[name="userEmail"]')?.value.trim();
            const websiteUrl = form.querySelector('input[name="websiteUrl"]')?.value.trim();
            const businessEmail = form.querySelector('input[name="businessEmail"]')?.value.trim();
            const emailOnSite = form.querySelector('input[name="emailOnSite"]:checked')?.value;

            // Photo (only if No)
            let photoFile = null;
            if (emailOnSite === 'no') {
                photoFile = form.querySelector('input[name="photo"]')?.files[0];
            }

            // Basic validation
            if (!fullName || !role || !companyName || !userEmail || !websiteUrl || !businessEmail || !emailOnSite) {
                showMessage('Please fill in all fields.', true);
                return;
            }
            if (emailOnSite === 'no' && !photoFile) {
                showMessage('Please upload a photo.', true);
                return;
            }

            try {
                new URL(websiteUrl);
            } catch (_) {
                showMessage('Please enter a valid website URL (e.g., https://example.com).', true);
                return;
            }

            if (!userEmail.includes('@') || !businessEmail.includes('@')) {
                showMessage('Please enter valid email addresses.', true);
                return;
            }

            const submitBtn = form.querySelector('button[type="submit"]');
            const originalBtnHTML = submitBtn.innerHTML;
            submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Submitting...';
            submitBtn.disabled = true;

            try {
                const formData = new FormData();
                formData.append('fullName', fullName);
                formData.append('role', role);
                formData.append('companyName', companyName);
                formData.append('userEmail', userEmail);
                formData.append('websiteUrl', websiteUrl);
                formData.append('businessEmail', businessEmail);
                formData.append('plan', plan);
                formData.append('emailOnSite', emailOnSite);
                if (photoFile) formData.append('photo', photoFile);

                const response = await fetch('/api/request_scan', {
                    method: 'POST',
                    body: formData
                });
                const data = await response.json();

                if (data.success) {
                    showMessage(data.message);
                    const parentSection = form.closest('.plan-url-section');
                    if (parentSection) parentSection.style.display = 'none';
                } else {
                    showMessage(data.message || 'Submission failed.', true);
                }
            } catch (error) {
                console.error('Submission error:', error);
                showMessage('An error occurred. Please try again later.', true);
            } finally {
                submitBtn.innerHTML = originalBtnHTML;
                submitBtn.disabled = false;
            }
        });
    });
});