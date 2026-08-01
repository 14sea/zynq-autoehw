library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity tb_axil_framebuf_write is
end entity;

architecture sim of tb_axil_framebuf_write is
  signal clk    : std_logic := '0';
  signal rstn   : std_logic := '0';
  signal rdaddr : std_logic_vector(10 downto 0) := (others => '0');
  signal rddata : std_logic_vector(31 downto 0);
  signal wraddr : std_logic_vector(10 downto 0) := (others => '0');
  signal wrdata : std_logic_vector(31 downto 0) := (others => '0');
  signal wren   : std_logic := '0';

  signal awaddr  : std_logic_vector(12 downto 0) := (others => '0');
  signal awvalid : std_logic := '0';
  signal awready : std_logic;
  signal wdata   : std_logic_vector(31 downto 0) := (others => '0');
  signal wstrb   : std_logic_vector(3 downto 0) := (others => '0');
  signal wvalid  : std_logic := '0';
  signal wready  : std_logic;
  signal bresp   : std_logic_vector(1 downto 0);
  signal bvalid  : std_logic;
  signal bready  : std_logic := '1';
  signal araddr  : std_logic_vector(12 downto 0) := (others => '0');
  signal arvalid : std_logic := '0';
  signal arready : std_logic;
  signal rdata   : std_logic_vector(31 downto 0);
  signal rresp   : std_logic_vector(1 downto 0);
  signal rvalid  : std_logic;
  signal rready  : std_logic := '1';
begin
  clk <= not clk after 5 ns;

  dut: entity work.axil_framebuf
    generic map (ADDR_BITS => 11)
    port map (
      s_axi_aclk    => clk,
      s_axi_aresetn => rstn,
      s_axi_awaddr  => awaddr,
      s_axi_awvalid => awvalid,
      s_axi_awready => awready,
      s_axi_wdata   => wdata,
      s_axi_wstrb   => wstrb,
      s_axi_wvalid  => wvalid,
      s_axi_wready  => wready,
      s_axi_bresp   => bresp,
      s_axi_bvalid  => bvalid,
      s_axi_bready  => bready,
      s_axi_araddr  => araddr,
      s_axi_arvalid => arvalid,
      s_axi_arready => arready,
      s_axi_rdata   => rdata,
      s_axi_rresp   => rresp,
      s_axi_rvalid  => rvalid,
      s_axi_rready  => rready,
      rd_addr       => rdaddr,
      rd_data       => rddata,
      wr_addr       => wraddr,
      wr_data       => wrdata,
      wr_en         => wren
    );

  stim: process
  begin
    wait for 20 ns;
    rstn <= '1';
    wait until rising_edge(clk);

    wraddr <= std_logic_vector(to_unsigned(1024, 11));
    wrdata <= x"43484D50";
    wren   <= '1';
    wait until rising_edge(clk);
    wren   <= '0';

    rdaddr <= std_logic_vector(to_unsigned(1024, 11));
    wait until rising_edge(clk);
    wait until rising_edge(clk);
    assert rddata = x"43484D50" report "NEORV32 write/readback mismatch" severity failure;

    awaddr  <= std_logic_vector(to_unsigned(4, 13));
    wdata   <= x"11223344";
    wstrb   <= "1111";
    awvalid <= '1';
    wvalid  <= '1';
    wait until rising_edge(clk);
    awvalid <= '0';
    wvalid  <= '0';
    wait until rising_edge(clk);

    rdaddr <= std_logic_vector(to_unsigned(1, 11));
    wait until rising_edge(clk);
    wait until rising_edge(clk);
    assert rddata = x"11223344" report "AXI write/readback mismatch" severity failure;
    assert bresp = "00" and rresp = "00" report "unexpected AXI response" severity failure;

    report "PASS";
    wait;
  end process;
end architecture;
