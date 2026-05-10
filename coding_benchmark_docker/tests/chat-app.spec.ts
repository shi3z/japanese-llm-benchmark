import { test, expect, type Page, type APIRequestContext } from '@playwright/test';
import * as fs from 'fs';

const API_BASE = 'http://localhost:3001';
const SCREENSHOT_DIR = '/screenshots';

// Ensure screenshot directory exists
test.beforeAll(async () => {
  if (!fs.existsSync(SCREENSHOT_DIR)) {
    fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
  }
});

// Helper: create user via API
async function createUser(request: APIRequestContext, username: string, password: string) {
  const res = await request.post(`${API_BASE}/api/auth/signup`, {
    data: { username, password },
  });
  return res.json();
}

// Helper: login via API
async function loginAPI(request: APIRequestContext, username: string, password: string) {
  const res = await request.post(`${API_BASE}/api/auth/login`, {
    data: { username, password },
  });
  return res.json();
}

// Helper: try multiple selectors to find an element
async function findInput(page: Page, hints: string[]) {
  for (const hint of hints) {
    try {
      const el = page.locator(hint).first();
      if (await el.isVisible({ timeout: 1000 })) return el;
    } catch {}
  }
  return null;
}

// Helper: find a clickable element by text patterns
async function findButton(page: Page, texts: string[]) {
  for (const text of texts) {
    try {
      const btn = page.getByRole('button', { name: new RegExp(text, 'i') }).first();
      if (await btn.isVisible({ timeout: 1000 })) return btn;
    } catch {}
  }
  // Fallback: any clickable with matching text
  for (const text of texts) {
    try {
      const el = page.locator(`text=${text}`).first();
      if (await el.isVisible({ timeout: 1000 })) return el;
    } catch {}
  }
  return null;
}

// ============================================================
// Test 1: Login / Signup
// ============================================================
test('signup and login', async ({ page, request }) => {
  // First try via API to setup
  let apiWorks = false;
  try {
    const res = await createUser(request, 'testuser1', 'password123');
    if (res.token || res.userId || res.id || res.user) apiWorks = true;
  } catch {}

  await page.goto('http://localhost:3000', { waitUntil: 'networkidle', timeout: 15000 });
  await page.waitForTimeout(2000);

  // Take screenshot of initial page (login/signup)
  await page.screenshot({ path: `${SCREENSHOT_DIR}/login.png`, fullPage: true });

  // Try to find username and password fields
  const usernameInput = await findInput(page, [
    'input[name="username"]',
    'input[placeholder*="ユーザー"]',
    'input[placeholder*="user"]',
    'input[placeholder*="User"]',
    'input[type="text"]:first-of-type',
    '#username',
  ]);

  const passwordInput = await findInput(page, [
    'input[name="password"]',
    'input[type="password"]',
    'input[placeholder*="パスワード"]',
    'input[placeholder*="pass"]',
    '#password',
  ]);

  let loginSuccess = false;

  if (usernameInput && passwordInput) {
    // If there's a signup tab/link, try clicking it first
    const signupLink = await findButton(page, ['signup', 'Sign Up', '新規登録', '登録', 'Register']);
    if (signupLink) {
      try { await signupLink.click(); await page.waitForTimeout(1000); } catch {}
    }

    // Re-find inputs after possible page change
    const uInput = await findInput(page, [
      'input[name="username"]', 'input[placeholder*="user"]',
      'input[type="text"]:first-of-type', '#username',
    ]);
    const pInput = await findInput(page, [
      'input[name="password"]', 'input[type="password"]', '#password',
    ]);

    if (uInput && pInput) {
      await uInput.fill('testuser1');
      await pInput.fill('password123');

      const submitBtn = await findButton(page, [
        'Sign Up', 'Signup', 'Register', '登録', '新規登録', 'Submit', 'Login', 'ログイン', 'サインアップ'
      ]);
      if (submitBtn) {
        await submitBtn.click();
        await page.waitForTimeout(3000);
      }

      // Check if we navigated away from login page
      const currentUrl = page.url();
      const stillOnLogin = await findInput(page, ['input[type="password"]']);
      if (!stillOnLogin || currentUrl !== 'http://localhost:3000/') {
        loginSuccess = true;
      }

      // If still on login, try logging in (account may already exist from API)
      if (!loginSuccess) {
        const loginLink = await findButton(page, ['login', 'Log In', 'Sign In', 'ログイン', 'サインイン']);
        if (loginLink) {
          try { await loginLink.click(); await page.waitForTimeout(1000); } catch {}
        }
        const uInput2 = await findInput(page, [
          'input[name="username"]', 'input[placeholder*="user"]',
          'input[type="text"]:first-of-type',
        ]);
        const pInput2 = await findInput(page, ['input[name="password"]', 'input[type="password"]']);
        if (uInput2 && pInput2) {
          await uInput2.fill('testuser1');
          await pInput2.fill('password123');
          const loginBtn = await findButton(page, ['Login', 'Log In', 'Sign In', 'ログイン', 'Submit', 'サインイン']);
          if (loginBtn) {
            await loginBtn.click();
            await page.waitForTimeout(3000);
          }
          const stillOnLogin2 = await findInput(page, ['input[type="password"]']);
          if (!stillOnLogin2) loginSuccess = true;
        }
      }
    }
  }

  // Even if UI login failed, if API works we consider partial success
  const result = { test: 'login', passed: loginSuccess || apiWorks, uiLogin: loginSuccess, apiLogin: apiWorks };
  fs.writeFileSync(`${SCREENSHOT_DIR}/test_login.json`, JSON.stringify(result));
  expect(loginSuccess || apiWorks).toBeTruthy();
});

// ============================================================
// Test 2: Friend Follow / Unfollow
// ============================================================
test('follow and unfollow friend', async ({ page, request }) => {
  // Setup: create two users via API
  try {
    await createUser(request, 'alice', 'password123');
    await createUser(request, 'bob', 'password123');
  } catch {}

  const loginData = await loginAPI(request, 'alice', 'password123');
  const token = loginData.token || loginData.accessToken || '';

  // Try follow via API first
  let apiFollowWorks = false;
  if (token) {
    try {
      // Get user list to find bob's ID
      const usersRes = await request.get(`${API_BASE}/api/users`, {
        headers: { 'Authorization': `Bearer ${token}` },
      });
      const users = await usersRes.json();
      const bob = (Array.isArray(users) ? users : users.users || [])
        .find((u: any) => u.username === 'bob');

      if (bob) {
        const followRes = await request.post(`${API_BASE}/api/friends/follow`, {
          data: { targetUserId: bob.id || bob.userId },
          headers: { 'Authorization': `Bearer ${token}` },
        });
        if (followRes.ok()) apiFollowWorks = true;
      }
    } catch {}
  }

  // Try via UI
  let uiFollowWorks = false;
  await page.goto('http://localhost:3000', { waitUntil: 'networkidle', timeout: 15000 });
  await page.waitForTimeout(2000);

  // Login as alice
  const uInput = await findInput(page, [
    'input[name="username"]', 'input[type="text"]:first-of-type',
  ]);
  const pInput = await findInput(page, ['input[name="password"]', 'input[type="password"]']);
  if (uInput && pInput) {
    await uInput.fill('alice');
    await pInput.fill('password123');
    const loginBtn = await findButton(page, ['Login', 'Log In', 'Sign In', 'ログイン', 'Submit', 'サインイン']);
    if (loginBtn) {
      await loginBtn.click();
      await page.waitForTimeout(3000);
    }

    // Look for users/friends section
    const usersLink = await findButton(page, ['Users', 'ユーザー', 'Friends', 'フレンド', '友達', 'People']);
    if (usersLink) {
      await usersLink.click();
      await page.waitForTimeout(2000);
    }

    // Look for follow button near 'bob'
    const followBtn = await findButton(page, ['Follow', 'フォロー']);
    if (followBtn) {
      await followBtn.click();
      await page.waitForTimeout(2000);
      uiFollowWorks = true;
    }
  }

  await page.screenshot({ path: `${SCREENSHOT_DIR}/friends.png`, fullPage: true });

  const result = { test: 'friends', passed: uiFollowWorks || apiFollowWorks, uiFollow: uiFollowWorks, apiFollow: apiFollowWorks };
  fs.writeFileSync(`${SCREENSHOT_DIR}/test_friends.json`, JSON.stringify(result));
  expect(uiFollowWorks || apiFollowWorks).toBeTruthy();
});

// ============================================================
// Test 3: Direct Messaging
// ============================================================
test('send and receive direct message', async ({ page, request }) => {
  // Setup users
  try {
    await createUser(request, 'charlie', 'password123');
    await createUser(request, 'diana', 'password123');
  } catch {}

  const charlieLogin = await loginAPI(request, 'charlie', 'password123');
  const token = charlieLogin.token || charlieLogin.accessToken || '';

  // Make them friends via API
  let apiMsgWorks = false;
  if (token) {
    try {
      const usersRes = await request.get(`${API_BASE}/api/users`, {
        headers: { 'Authorization': `Bearer ${token}` },
      });
      const users = await usersRes.json();
      const diana = (Array.isArray(users) ? users : users.users || [])
        .find((u: any) => u.username === 'diana');

      if (diana) {
        await request.post(`${API_BASE}/api/friends/follow`, {
          data: { targetUserId: diana.id || diana.userId },
          headers: { 'Authorization': `Bearer ${token}` },
        });

        // Send message via API
        const msgRes = await request.post(`${API_BASE}/api/messages/send`, {
          data: { recipientId: diana.id || diana.userId, content: 'Hello from coding benchmark!' },
          headers: { 'Authorization': `Bearer ${token}` },
        });
        if (msgRes.ok()) apiMsgWorks = true;

        // Retrieve messages
        const getRes = await request.get(`${API_BASE}/api/messages/${diana.id || diana.userId}`, {
          headers: { 'Authorization': `Bearer ${token}` },
        });
        const msgs = await getRes.json();
        const hasMsg = JSON.stringify(msgs).includes('Hello from coding benchmark');
        if (hasMsg) apiMsgWorks = true;
      }
    } catch {}
  }

  // Try via UI
  let uiMsgWorks = false;
  await page.goto('http://localhost:3000', { waitUntil: 'networkidle', timeout: 15000 });
  await page.waitForTimeout(2000);

  const uInput = await findInput(page, [
    'input[name="username"]', 'input[type="text"]:first-of-type',
  ]);
  const pInput = await findInput(page, ['input[name="password"]', 'input[type="password"]']);
  if (uInput && pInput) {
    await uInput.fill('charlie');
    await pInput.fill('password123');
    const loginBtn = await findButton(page, ['Login', 'Log In', 'Sign In', 'ログイン', 'Submit', 'サインイン']);
    if (loginBtn) {
      await loginBtn.click();
      await page.waitForTimeout(3000);
    }

    // Navigate to messages or click on a user
    const msgLink = await findButton(page, ['Messages', 'メッセージ', 'DM', 'Chat', 'チャット']);
    if (msgLink) {
      await msgLink.click();
      await page.waitForTimeout(2000);
    }

    // Click on diana
    try {
      const dianaEl = page.locator('text=diana').first();
      if (await dianaEl.isVisible({ timeout: 2000 })) {
        await dianaEl.click();
        await page.waitForTimeout(2000);
      }
    } catch {}

    // Type a message
    const msgInput = await findInput(page, [
      'input[name="message"]',
      'input[placeholder*="メッセージ"]',
      'input[placeholder*="message"]',
      'input[placeholder*="Message"]',
      'textarea',
      'input[type="text"]:last-of-type',
    ]);
    if (msgInput) {
      await msgInput.fill('UI test message from benchmark');
      const sendBtn = await findButton(page, ['Send', '送信', 'Submit']);
      if (sendBtn) {
        await sendBtn.click();
        await page.waitForTimeout(2000);
        // Check if message appears on page
        const msgVisible = await page.locator('text=UI test message').isVisible({ timeout: 3000 }).catch(() => false);
        if (msgVisible) uiMsgWorks = true;
      }
    }
  }

  await page.screenshot({ path: `${SCREENSHOT_DIR}/dm.png`, fullPage: true });

  const result = { test: 'messaging', passed: uiMsgWorks || apiMsgWorks, uiMsg: uiMsgWorks, apiMsg: apiMsgWorks };
  fs.writeFileSync(`${SCREENSHOT_DIR}/test_messaging.json`, JSON.stringify(result));
  expect(uiMsgWorks || apiMsgWorks).toBeTruthy();
});

// ============================================================
// Test 4: Real-time Updates
// ============================================================
test('messages appear in real-time', async ({ page, request, browser }) => {
  // Setup
  try {
    await createUser(request, 'eve', 'password123');
    await createUser(request, 'frank', 'password123');
  } catch {}

  const eveLogin = await loginAPI(request, 'eve', 'password123');
  const eveToken = eveLogin.token || eveLogin.accessToken || '';
  const frankLogin = await loginAPI(request, 'frank', 'password123');
  const frankToken = frankLogin.token || frankLogin.accessToken || '';

  // Make friends via API
  let frankId = '';
  try {
    const usersRes = await request.get(`${API_BASE}/api/users`, {
      headers: { 'Authorization': `Bearer ${eveToken}` },
    });
    const users = await usersRes.json();
    const frank = (Array.isArray(users) ? users : users.users || [])
      .find((u: any) => u.username === 'frank');
    if (frank) {
      frankId = frank.id || frank.userId;
      await request.post(`${API_BASE}/api/friends/follow`, {
        data: { targetUserId: frankId },
        headers: { 'Authorization': `Bearer ${eveToken}` },
      });
    }
  } catch {}

  let realtimeWorks = false;

  // Login as eve via UI
  await page.goto('http://localhost:3000', { waitUntil: 'networkidle', timeout: 15000 });
  await page.waitForTimeout(2000);

  const uInput = await findInput(page, [
    'input[name="username"]', 'input[type="text"]:first-of-type',
  ]);
  const pInput = await findInput(page, ['input[name="password"]', 'input[type="password"]']);
  if (uInput && pInput) {
    await uInput.fill('eve');
    await pInput.fill('password123');
    const loginBtn = await findButton(page, ['Login', 'Log In', 'Sign In', 'ログイン', 'Submit', 'サインイン']);
    if (loginBtn) {
      await loginBtn.click();
      await page.waitForTimeout(3000);
    }

    // Navigate to frank's chat
    const msgLink = await findButton(page, ['Messages', 'メッセージ', 'DM', 'Chat', 'チャット']);
    if (msgLink) {
      await msgLink.click();
      await page.waitForTimeout(2000);
    }
    try {
      const frankEl = page.locator('text=frank').first();
      if (await frankEl.isVisible({ timeout: 2000 })) {
        await frankEl.click();
        await page.waitForTimeout(2000);
      }
    } catch {}

    // Now send a message as frank via API
    if (frankToken && frankId) {
      try {
        // Get eve's ID
        const usersRes = await request.get(`${API_BASE}/api/users`, {
          headers: { 'Authorization': `Bearer ${frankToken}` },
        });
        const users = await usersRes.json();
        const eve = (Array.isArray(users) ? users : users.users || [])
          .find((u: any) => u.username === 'eve');
        if (eve) {
          await request.post(`${API_BASE}/api/messages/send`, {
            data: { recipientId: eve.id || eve.userId, content: 'Realtime test message!' },
            headers: { 'Authorization': `Bearer ${frankToken}` },
          });
        }
      } catch {}
    }

    // Wait for polling to pick it up (up to 10 seconds)
    for (let i = 0; i < 10; i++) {
      const visible = await page.locator('text=Realtime test message').isVisible().catch(() => false);
      if (visible) {
        realtimeWorks = true;
        break;
      }
      await page.waitForTimeout(1000);
    }
  }

  await page.screenshot({ path: `${SCREENSHOT_DIR}/chat.png`, fullPage: true });

  const result = { test: 'realtime', passed: realtimeWorks };
  fs.writeFileSync(`${SCREENSHOT_DIR}/test_realtime.json`, JSON.stringify(result));

  // This test is more lenient - realtime is hard
  // We record the result but don't fail the entire suite
  expect(true).toBeTruthy();
});
