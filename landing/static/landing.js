const revealNodes = document.querySelectorAll(".reveal");
const canAnimateReveal =
  document.documentElement.classList.contains("reveal-enhanced") && "IntersectionObserver" in window;

if (canAnimateReveal) {
  const revealObserver = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("is-visible");
          revealObserver.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.16 }
  );

  revealNodes.forEach((node) => revealObserver.observe(node));
} else {
  revealNodes.forEach((node) => node.classList.add("is-visible"));
}

const body = document.body;
const topbar = document.querySelector("[data-topbar]");

const syncScrollState = () => {
  if (!topbar) {
    return;
  }
  body.classList.toggle("is-scrolled", window.scrollY > 24);
};

syncScrollState();
window.addEventListener("scroll", syncScrollState, { passive: true });

document.querySelectorAll('a[href^="#"]').forEach((anchor) => {
  anchor.addEventListener("click", (event) => {
    const href = anchor.getAttribute("href");
    if (!href || href === "#") {
      return;
    }
    const target = document.querySelector(href);
    if (!target) {
      return;
    }
    event.preventDefault();
    target.scrollIntoView({ behavior: "smooth", block: "start" });
  });
});

const finePointer = window.matchMedia("(hover: hover) and (pointer: fine)").matches;

if (finePointer) {
  document.querySelectorAll(".essence-card, .location-card, .system-card, .cta-panel, .signal-chip").forEach((card) => {
    card.addEventListener("mousemove", (event) => {
      const bounds = card.getBoundingClientRect();
      const x = ((event.clientX - bounds.left) / bounds.width - 0.5) * 4;
      const y = ((event.clientY - bounds.top) / bounds.height - 0.5) * -4;
      card.style.transform = `translateY(-6px) rotateX(${y}deg) rotateY(${x}deg)`;
    });

    card.addEventListener("mouseleave", () => {
      card.style.transform = "";
    });
  });
}

const consentKey = "amonora_cookie_consent";
const banner = document.querySelector("[data-cookie-banner]");
const modal = document.querySelector("[data-cookie-modal]");
const analyticsToggle = document.querySelector("[data-cookie-analytics]");

const readConsent = () => {
  try {
    return JSON.parse(localStorage.getItem(consentKey) || "null");
  } catch {
    return null;
  }
};

const writeConsent = (analytics) => {
  localStorage.setItem(
    consentKey,
    JSON.stringify({
      necessary: true,
      analytics: Boolean(analytics),
      savedAt: new Date().toISOString(),
    })
  );
};

const applyConsentUI = () => {
  const consent = readConsent();
  if (!banner) {
    return;
  }
  banner.hidden = Boolean(consent);
  document.body.classList.toggle("has-cookie-banner", !consent);
  if (analyticsToggle) {
    analyticsToggle.checked = Boolean(consent?.analytics);
  }
};

const openCookieModal = () => {
  if (!modal) {
    return;
  }
  modal.hidden = false;
  document.body.classList.add("cookie-modal-open");
};

const closeCookieModal = () => {
  if (!modal) {
    return;
  }
  modal.hidden = true;
  document.body.classList.remove("cookie-modal-open");
};

document.querySelectorAll("[data-cookie-settings]").forEach((node) => {
  node.addEventListener("click", openCookieModal);
});

document.querySelectorAll("[data-cookie-close]").forEach((node) => {
  node.addEventListener("click", closeCookieModal);
});

document.querySelectorAll("[data-cookie-accept]").forEach((node) => {
  node.addEventListener("click", () => {
    writeConsent(true);
    applyConsentUI();
    closeCookieModal();
  });
});

document.querySelectorAll("[data-cookie-essential]").forEach((node) => {
  node.addEventListener("click", () => {
    writeConsent(false);
    applyConsentUI();
    closeCookieModal();
  });
});

document.querySelectorAll("[data-cookie-save]").forEach((node) => {
  node.addEventListener("click", () => {
    writeConsent(Boolean(analyticsToggle?.checked));
    applyConsentUI();
    closeCookieModal();
  });
});

applyConsentUI();

const bridgeRequestButton = document.querySelector("[data-bridge-request]");
const bridgeError = document.querySelector("[data-bridge-error]");
const bridgeResult = document.querySelector("[data-bridge-result]");
const bridgeCountry = document.querySelector("[data-bridge-country]");
const bridgeExpires = document.querySelector("[data-bridge-expires]");
const bridgeKeyOutput = document.querySelector("[data-bridge-key]");
const bridgeCopyButton = document.querySelector("[data-bridge-copy]");

const seedSakuraElements = () => {
  const petals = document.querySelectorAll("[data-sakura-petal]");
  petals.forEach((petal) => {
    const size = 6 + Math.random() * 16;
    const duration = 14 + Math.random() * 20;
    const delay = -Math.random() * duration;
    const x = Math.random() * 100;
    const drift = (Math.random() * 80 - 40).toFixed(0);
    const opacity = (0.3 + Math.random() * 0.5).toFixed(2);
    const blur = Math.random() > 0.7 ? (0.8 + Math.random() * 1.6).toFixed(2) : "0";
    const rotate = (Math.random() * 140 - 70).toFixed(0);
    petal.style.setProperty("--petal-size", `${size.toFixed(1)}px`);
    petal.style.setProperty("--petal-duration", `${duration.toFixed(1)}s`);
    petal.style.setProperty("--petal-delay", `${delay.toFixed(1)}s`);
    petal.style.setProperty("--petal-x", `${x.toFixed(1)}%`);
    petal.style.setProperty("--petal-drift", `${drift}px`);
    petal.style.setProperty("--petal-opacity", opacity);
    petal.style.setProperty("--petal-blur", `${blur}px`);
    petal.style.setProperty("--petal-rotate", `${rotate}deg`);
  });

  const dust = document.querySelectorAll("[data-sakura-dust]");
  dust.forEach((particle) => {
    const size = 1 + Math.random() * 3;
    const duration = 10 + Math.random() * 12;
    const delay = -Math.random() * duration;
    const x = Math.random() * 100;
    const y = Math.random() * 90;
    const opacity = (0.25 + Math.random() * 0.45).toFixed(2);
    particle.style.setProperty("--dust-size", `${size.toFixed(1)}px`);
    particle.style.setProperty("--dust-duration", `${duration.toFixed(1)}s`);
    particle.style.setProperty("--dust-delay", `${delay.toFixed(1)}s`);
    particle.style.setProperty("--dust-x", `${x.toFixed(1)}%`);
    particle.style.setProperty("--dust-y", `${y.toFixed(1)}%`);
    particle.style.setProperty("--dust-opacity", opacity);
  });
};

seedSakuraElements();

const heroVisual = document.getElementById("heroVisual");
const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

if (heroVisual && finePointer && !reduceMotion) {
  heroVisual.addEventListener("mousemove", (event) => {
    const bounds = heroVisual.getBoundingClientRect();
    const x = event.clientX - bounds.left;
    const y = event.clientY - bounds.top;
    const rotateY = ((x / bounds.width) - 0.5) * 10;
    const rotateX = ((y / bounds.height) - 0.5) * -10;

    heroVisual.style.transform = `translateY(-4px) rotateX(${rotateX.toFixed(2)}deg) rotateY(${rotateY.toFixed(2)}deg)`;
  });

  heroVisual.addEventListener("mouseleave", () => {
    heroVisual.style.transform = "";
  });
}

const setBridgePendingState = (pending) => {
  if (!bridgeRequestButton) {
    return;
  }
  bridgeRequestButton.disabled = pending;
  bridgeRequestButton.textContent = pending ? "Готовим ключ..." : "Получить ключ на 1 день";
};

const showBridgeError = (message) => {
  if (!bridgeError) {
    return;
  }
  bridgeError.hidden = false;
  bridgeError.textContent = message;
};

const clearBridgeError = () => {
  if (!bridgeError) {
    return;
  }
  bridgeError.hidden = true;
  bridgeError.textContent = "";
};

if (bridgeRequestButton && bridgeResult && bridgeCountry && bridgeExpires && bridgeKeyOutput) {
  bridgeRequestButton.addEventListener("click", async () => {
    clearBridgeError();
    bridgeResult.hidden = true;
    setBridgePendingState(true);

    try {
      const response = await fetch("/bridge/access", {
        method: "POST",
        headers: {
          Accept: "application/json",
        },
        cache: "no-store",
      });
      const payload = await response.json();

      if (!response.ok || !payload.ok) {
        throw new Error(payload.message || "Не удалось получить временный ключ.");
      }

      bridgeCountry.textContent = payload.data.country_name || "—";
      bridgeExpires.textContent = payload.data.access_expires_at || "—";
      bridgeKeyOutput.value = payload.data.vless_link || "";
      bridgeResult.hidden = false;
      bridgeResult.scrollIntoView({ behavior: "smooth", block: "nearest" });
    } catch (error) {
      showBridgeError(error instanceof Error ? error.message : "Не удалось получить временный ключ.");
    } finally {
      setBridgePendingState(false);
    }
  });
}

if (bridgeCopyButton && bridgeKeyOutput) {
  bridgeCopyButton.addEventListener("click", async () => {
    const value = bridgeKeyOutput.value.trim();
    if (!value) {
      return;
    }
    try {
      await navigator.clipboard.writeText(value);
      bridgeCopyButton.textContent = "Скопировано";
      window.setTimeout(() => {
        bridgeCopyButton.textContent = "Скопировать ключ";
      }, 1600);
    } catch {
      bridgeKeyOutput.focus();
      bridgeKeyOutput.select();
      document.execCommand("copy");
      bridgeCopyButton.textContent = "Скопировано";
      window.setTimeout(() => {
        bridgeCopyButton.textContent = "Скопировать ключ";
      }, 1600);
    }
  });
}
