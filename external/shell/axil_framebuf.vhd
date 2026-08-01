-- axil_framebuf.vhd - AXI4-Lite slave backing two disjoint 32-bit RAM windows.
-- Low half: PS-written parameter/restore RAM. High half: NEORV32-written
-- board-origin champion/replay store. Each half has exactly one writer and two
-- readers, preserving a Vivado-supported BRAM template.
library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity axil_framebuf is
  generic (
    ADDR_BITS : positive := 11  -- 2048 words by default; EHW-3.4 uses 14.
  );
  port (
    s_axi_aclk    : in  std_logic;
    s_axi_aresetn : in  std_logic;
    -- AXI4-Lite slave (PS writes the payload; reads supported for debug)
    s_axi_awaddr  : in  std_logic_vector(ADDR_BITS+1 downto 0);
    s_axi_awvalid : in  std_logic;
    s_axi_awready : out std_logic;
    s_axi_wdata   : in  std_logic_vector(31 downto 0);
    s_axi_wstrb   : in  std_logic_vector(3 downto 0);
    s_axi_wvalid  : in  std_logic;
    s_axi_wready  : out std_logic;
    s_axi_bresp   : out std_logic_vector(1 downto 0);
    s_axi_bvalid  : out std_logic;
    s_axi_bready  : in  std_logic;
    s_axi_araddr  : in  std_logic_vector(ADDR_BITS+1 downto 0);
    s_axi_arvalid : in  std_logic;
    s_axi_arready : out std_logic;
    s_axi_rdata   : out std_logic_vector(31 downto 0);
    s_axi_rresp   : out std_logic_vector(1 downto 0);
    s_axi_rvalid  : out std_logic;
    s_axi_rready  : in  std_logic;
    -- NEORV32 registered read port
    rd_addr       : in  std_logic_vector(ADDR_BITS-1 downto 0);
    rd_data       : out std_logic_vector(31 downto 0);
    -- NEORV32 full-word write port into the high-half store window.
    wr_addr       : in  std_logic_vector(ADDR_BITS-1 downto 0) := (others => '0');
    wr_data       : in  std_logic_vector(31 downto 0) := (others => '0');
    wr_en         : in  std_logic := '0'
  );
end entity;

architecture rtl of axil_framebuf is
  constant DEPTH : natural := 2 ** ADDR_BITS;
  constant HALF_DEPTH : natural := DEPTH / 2;
  type ram_t is array(0 to HALF_DEPTH-1) of std_logic_vector(31 downto 0);
  signal param_ram : ram_t := (others => (others => '0'));
  signal store_ram : ram_t := (others => (others => '0'));

  signal awready_r, wready_r, bvalid_r : std_logic := '0';
  signal arready_r, rvalid_r           : std_logic := '0';
  signal rdata_param_r                 : std_logic_vector(31 downto 0) := (others => '0');
  signal rdata_store_r                 : std_logic_vector(31 downto 0) := (others => '0');
  signal rsel_r                        : std_logic := '0';
  signal rd_param_r                    : std_logic_vector(31 downto 0) := (others => '0');
  signal rd_store_r                    : std_logic_vector(31 downto 0) := (others => '0');
  signal rdsel_r                       : std_logic := '0';

  function low_index(addr : std_logic_vector(ADDR_BITS-1 downto 0)) return integer is
  begin
    return to_integer(unsigned(addr(ADDR_BITS-2 downto 0)));
  end function;
begin
  s_axi_awready <= awready_r;
  s_axi_wready  <= wready_r;
  s_axi_bvalid  <= bvalid_r;
  s_axi_bresp   <= "00";
  s_axi_arready <= arready_r;
  s_axi_rvalid  <= rvalid_r;
  s_axi_rresp   <= "00";
  s_axi_rdata   <= rdata_store_r when rsel_r = '1' else rdata_param_r;
  rd_data       <= rd_store_r when rdsel_r = '1' else rd_param_r;

  -- write channel: accept aw+w together, write RAM, single bresp
  wr: process(s_axi_aclk)
    variable word_addr : std_logic_vector(ADDR_BITS-1 downto 0);
    variable wi : integer range 0 to HALF_DEPTH-1;
    variable nwi : integer range 0 to HALF_DEPTH-1;
  begin
    if rising_edge(s_axi_aclk) then
      if s_axi_aresetn = '0' then
        awready_r <= '0'; wready_r <= '0'; bvalid_r <= '0';
      else
        awready_r <= '0'; wready_r <= '0';
        if (s_axi_awvalid = '1' and s_axi_wvalid = '1' and awready_r = '0'
            and wready_r = '0' and bvalid_r = '0') then
          awready_r <= '1'; wready_r <= '1';
          word_addr := s_axi_awaddr(ADDR_BITS+1 downto 2);
          if word_addr(ADDR_BITS-1) = '0' then
            wi := low_index(word_addr);
            for b in 0 to 3 loop
              if s_axi_wstrb(b) = '1' then
                param_ram(wi)(b*8+7 downto b*8) <= s_axi_wdata(b*8+7 downto b*8);
              end if;
            end loop;
          end if;
          bvalid_r <= '1';
        elsif (bvalid_r = '1' and s_axi_bready = '1') then
          bvalid_r <= '0';
        end if;
        if wr_en = '1' and wr_addr(ADDR_BITS-1) = '1' then
          nwi := low_index(wr_addr);
          store_ram(nwi) <= wr_data;
        end if;
      end if;
    end if;
  end process;

  -- read channel (AXI side, for debug and PS fatwrite)
  rd: process(s_axi_aclk)
    variable word_addr : std_logic_vector(ADDR_BITS-1 downto 0);
    variable ri : integer range 0 to HALF_DEPTH-1;
  begin
    if rising_edge(s_axi_aclk) then
      if s_axi_aresetn = '0' then
        arready_r <= '0'; rvalid_r <= '0';
      else
        arready_r <= '0';
        if (s_axi_arvalid = '1' and arready_r = '0' and rvalid_r = '0') then
          arready_r <= '1';
          word_addr := s_axi_araddr(ADDR_BITS+1 downto 2);
          ri := low_index(word_addr);
          rdata_param_r <= param_ram(ri);
          rdata_store_r <= store_ram(ri);
          rsel_r        <= word_addr(ADDR_BITS-1);
          rvalid_r  <= '1';
        elsif (rvalid_r = '1' and s_axi_rready = '1') then
          rvalid_r <= '0';
        end if;
      end if;
    end if;
  end process;

  -- NEORV32 read port (registered, 1-cycle latency)
  nrd: process(s_axi_aclk)
    variable ri : integer range 0 to HALF_DEPTH-1;
  begin
    if rising_edge(s_axi_aclk) then
      ri := low_index(rd_addr);
      rd_param_r <= param_ram(ri);
      rd_store_r <= store_ram(ri);
      rdsel_r    <= rd_addr(ADDR_BITS-1);
    end if;
  end process;
end architecture;
