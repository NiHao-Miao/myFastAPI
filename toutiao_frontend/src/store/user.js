/**
 * 用户状态：accessToken（JWT）+ refreshToken（随机串）。
 * - accessToken 随每个业务请求发送，过期后由 http.js / authFetch 自动刷新；
 * - refreshToken 只用于 /api/user/refresh 和 /api/user/logout；
 * - 两者都通过 pinia-plugin-persistedstate 持久化到 localStorage。
 */
import { defineStore } from 'pinia';
import axios from 'axios';
import { apiConfig } from '../config/api';

export const useUserStore = defineStore('user', {
  state: () => ({
    userInfo: null,
    token: '',          // 访问令牌（JWT）。保留原名，页面里的 userStore.token 不用全改
    refreshToken: '',   // 刷新令牌
    isLogin: false,
    userBio: '这是我的个人简介'
  }),

  getters: {
    getUserInfo: (state) => state.userInfo,
    getToken: (state) => state.token,
    getLoginStatus: (state) => state.isLogin,
    getUserBio: (state) => state.userInfo?.bio || state.userBio
  },

  actions: {
    // 保存登录/注册响应里的双令牌和用户信息
    _applyAuthData(data) {
      if (!data) return;
      if (data.userInfo) {
        this.userInfo = data.userInfo;
      }
      this.token = data.accessToken || data.token || '';
      this.refreshToken = data.refreshToken || '';
      this.isLogin = Boolean(this.token);
    },

    // 清空本地登录态（不调后端）
    _clearAuth() {
      this.userInfo = null;
      this.token = '';
      this.refreshToken = '';
      this.isLogin = false;
    },

    async login(userData) {
      try {
        const response = await axios.post(`${apiConfig.baseURL}/api/user/login`, {
          username: userData.username,
          password: userData.password
        });

        if (response.data && response.data.code === 200) {
          this._applyAuthData(response.data.data);
          return { success: true, message: '登录成功' };
        }

        return {
          success: false,
          message: response.data?.message || '登录失败'
        };
      } catch (error) {
        console.error('登录请求失败:', error);
        return {
          success: false,
          message: error.response?.data?.message || '登录请求失败，请稍后再试'
        };
      }
    },

    async register(userData) {
      try {
        const response = await axios.post(`${apiConfig.baseURL}/api/user/register`, {
          username: userData.username,
          password: userData.password
        });

        if (response.data && response.data.code === 200) {
          this._applyAuthData(response.data.data);
          return { success: true, message: '注册成功' };
        }

        return {
          success: false,
          message: response.data?.message || '注册失败'
        };
      } catch (error) {
        console.error('注册请求失败:', error);
        return {
          success: false,
          message: error.response?.data?.message || '注册请求失败，请稍后再试'
        };
      }
    },

    // 登出：先清本地，再通知后端撤销刷新令牌（失败也不影响本地退出）
    async logout() {
      const refreshToken = this.refreshToken;
      this._clearAuth();

      if (!refreshToken) return;

      try {
        await axios.post(`${apiConfig.baseURL}/api/user/logout`, { refreshToken });
      } catch (error) {
        console.warn('登出接口调用失败（本地登录态已清除）:', error);
      }
    },

    // 用刷新令牌换新的访问令牌
    async refreshAccessToken() {
      if (!this.refreshToken) return false;

      try {
        const response = await axios.post(`${apiConfig.baseURL}/api/user/refresh`, {
          refreshToken: this.refreshToken
        });

        const data = response.data?.data;
        if (response.data?.code === 200 && data?.accessToken) {
          this.token = data.accessToken;
          this.isLogin = true;
          return true;
        }

        return false;
      } catch (error) {
        console.warn('刷新访问令牌失败:', error);
        // 只有明确 401 才清空；网络错误保留状态，允许用户重试
        if (error.response?.status === 401) {
          this._clearAuth();
        }
        return false;
      }
    },

    // 带 Bearer 头的 axios 请求；401 时自动刷新并重试一次
    async requestWithAuth(config) {
      const send = () => axios({
        ...config,
        headers: {
          ...(config.headers || {}),
          Authorization: `Bearer ${this.token}`
        }
      });

      try {
        return await send();
      } catch (error) {
        if (error.response?.status === 401) {
          const refreshed = await this.refreshAccessToken();
          if (refreshed) {
            return send();
          }
        }
        throw error;
      }
    },

    // 获取用户信息
    async getUserInfoDetail() {
      try {
        if (!this.token && !this.refreshToken) {
          return { success: false, message: '未登录' };
        }

        const response = await this.requestWithAuth({
          method: 'get',
          url: `${apiConfig.baseURL}/api/user/info`
        });

        if (response.data && response.data.code === 200) {
          this.userInfo = response.data.data;
          return {
            success: true,
            message: '获取用户信息成功',
            data: response.data.data
          };
        }

        return {
          success: false,
          message: response.data?.message || '获取用户信息失败'
        };
      } catch (error) {
        console.error('获取用户信息请求失败:', error);
        return {
          success: false,
          message: error.response?.data?.message || '获取用户信息请求失败，请稍后再试'
        };
      }
    },

    // 更新个人简介
    async updateUserBio(bio) {
      try {
        if (!this.token && !this.refreshToken) {
          return { success: false, message: '未登录' };
        }

        const response = await this.requestWithAuth({
          method: 'put',
          url: `${apiConfig.baseURL}/api/user/update`,
          data: { bio }
        });

        if (response.data && response.data.code === 200) {
          if (this.userInfo) {
            this.userInfo.bio = bio;
          }
          return { success: true, message: '更新个人简介成功' };
        }

        return {
          success: false,
          message: response.data?.message || '更新个人简介失败'
        };
      } catch (error) {
        console.error('更新个人简介请求失败:', error);
        return {
          success: false,
          message: error.response?.data?.message || '更新个人简介请求失败，请稍后再试'
        };
      }
    },

    // 修改密码
    async updatePassword(oldPassword, newPassword) {
      try {
        if (!this.token && !this.refreshToken) {
          return { success: false, message: '未登录' };
        }

        const response = await this.requestWithAuth({
          method: 'put',
          url: `${apiConfig.baseURL}/api/user/password`,
          data: { oldPassword, newPassword }
        });

        if (response.data && response.data.code === 200) {
          // 后端已撤销刷新令牌；本地也清空，要求重新登录
          this._clearAuth();
          return { success: true, message: '密码修改成功，请重新登录' };
        }

        return {
          success: false,
          message: response.data?.message || '密码修改失败'
        };
      } catch (error) {
        console.error('修改密码请求失败:', error);
        return {
          success: false,
          message: error.response?.data?.message || '修改密码请求失败，请稍后再试'
        };
      }
    }
  },

  // pinia-plugin-persistedstate v4 的写法
  persist: {
    key: 'user-store',
    storage: localStorage,
    pick: ['userInfo', 'token', 'refreshToken', 'isLogin']
  }
});